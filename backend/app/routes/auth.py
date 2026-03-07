from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity
)
from datetime import timedelta, datetime
import secrets

from ..extensions import db, bcrypt
from ..models import User, PasswordResetToken
from ..utils.email import send_reset_email

# ── Blueprint ─────────────────────────────────────────────────
auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ── Helper ────────────────────────────────────────────────────
def error(message, code=400):
    """Shortcut for returning JSON error responses."""
    return jsonify({"success": False, "message": message}), code


def success(message, data=None, code=200):
    """Shortcut for returning JSON success responses."""
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code


# ── POST /api/auth/register ───────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Registers a new customer account.

    Request body (JSON):
        name     : string, required
        email    : string, required, unique
        password : string, required, min 8 chars
        phone    : string, optional

    Returns:
        201 → user created, access token, refresh token
        400 → validation error
        409 → email already exists
    """
    data = request.get_json()

    # ── Validate required fields ──────────────────────────────
    if not data:
        return error("Request body is required")

    name     = data.get("name",     "").strip()
    email    = data.get("email",    "").strip().lower()
    password = data.get("password", "").strip()
    phone    = (data.get("phone") or "").strip() or None

    if not name:
        return error("Name is required")
    if not email:
        return error("Email is required")
    if not password:
        return error("Password is required")
    if len(password) < 8:
        return error("Password must be at least 8 characters")

    # ── Check duplicate email ──────────────────────────────────
    if User.query.filter_by(email=email).first():
        return error("An account with this email already exists", 409)

    # ── Hash password ─────────────────────────────────────────
    password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    # ── Create user ───────────────────────────────────────────
    user = User(
        name          = name,
        email         = email,
        phone         = phone,
        password_hash = password_hash,
        role          = "customer"
    )
    db.session.add(user)
    db.session.commit()

    # ── Generate tokens ───────────────────────────────────────
    access_token  = create_access_token(
        identity  = str(user.id),
        expires_delta = timedelta(days=1)
    )
    refresh_token = create_refresh_token(
        identity  = str(user.id),
        expires_delta = timedelta(days=30)
    )

    return success(
        message = "Account created successfully",
        data    = {
            "user":          user.to_dict(),
            "access_token":  access_token,
            "refresh_token": refresh_token
        },
        code = 201
    )


# ── POST /api/auth/login ──────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Logs in an existing user.

    Request body (JSON):
        email    : string, required
        password : string, required

    Returns:
        200 → access token, refresh token, user data
        400 → missing fields
        401 → invalid credentials
        403 → account deactivated
    """
    data = request.get_json()

    if not data:
        return error("Request body is required")

    email    = data.get("email",    "").strip().lower()
    password = data.get("password", "").strip()

    if not email or not password:
        return error("Email and password are required")

    # ── Find user ─────────────────────────────────────────────
    user = User.query.filter_by(email=email).first()

    # ── Verify password ───────────────────────────────────────
    # Always check both user existence AND password together.
    # Never reveal which one failed — security best practice.
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return error("Invalid email or password", 401)

    # ── Check account is active ───────────────────────────────
    if not user.is_active:
        return error("Your account has been deactivated. Please contact support.", 403)

    # ── Generate tokens ───────────────────────────────────────
    access_token  = create_access_token(
        identity      = str(user.id),
        expires_delta = timedelta(days=1)
    )
    refresh_token = create_refresh_token(
        identity      = str(user.id),
        expires_delta = timedelta(days=30)
    )

    return success(
        message = "Login successful",
        data    = {
            "user":          user.to_dict(),
            "access_token":  access_token,
            "refresh_token": refresh_token
        }
    )


# ── POST /api/auth/refresh ────────────────────────────────────
@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """
    Issues a new access token using a valid refresh token.
    Called automatically by frontend when access token expires.

    Header:
        Authorization: Bearer <refresh_token>

    Returns:
        200 → new access token
        401 → invalid or expired refresh token
    """
    user_id      = get_jwt_identity()
    access_token = create_access_token(
        identity      = user_id,
        expires_delta = timedelta(days=1)
    )

    return success(
        message = "Token refreshed",
        data    = {"access_token": access_token}
    )


# ── GET /api/auth/me ──────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    """
    Returns current logged-in user's profile.
    Frontend calls this on page load to check if still logged in.

    Header:
        Authorization: Bearer <access_token>

    Returns:
        200 → user data
        401 → not logged in
    """
    user_id = get_jwt_identity()
    user    = User.query.get(int(user_id))

    if not user or not user.is_active:
        return error("User not found", 404)

    return success(
        message = "Profile fetched",
        data    = {"user": user.to_dict()}
    )


# ── POST /api/auth/forgot-password ───────────────────────────
@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """
    Generates a password reset token and sends email.

    Request body (JSON):
        email : string, required

    Returns:
        200 → always returns success (security — never reveal if email exists)
        400 → missing email
    """
    data  = request.get_json()
    email = data.get("email", "").strip().lower() if data else ""

    if not email:
        return error("Email is required")

    user = User.query.filter_by(email=email).first()

    # Always return success even if email not found.
    # This prevents attackers from discovering registered emails.
    if not user:
        return success("If this email exists, a reset link has been sent")

    # ── Invalidate old tokens ─────────────────────────────────
    PasswordResetToken.query.filter_by(
        user_id = user.id,
        used    = False
    ).delete()

    # ── Create new token ──────────────────────────────────────
    token = PasswordResetToken(
        user_id    = user.id,
        token      = secrets.token_urlsafe(32),
        expires_at = datetime.utcnow() + timedelta(hours=1)
    )
    db.session.add(token)
    db.session.commit()

    # ── Send email ────────────────────────────────────────────
    try:
        send_reset_email(user.email, token.token)
    except Exception as e:
        current_app.logger.error(f"Failed to send reset email to {user.email}: {e}")

    return success("If this email exists, a reset link has been sent")


# ── POST /api/auth/reset-password ────────────────────────────
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """
    Resets password using a valid reset token.

    Request body (JSON):
        token       : string, required
        new_password: string, required, min 8 chars

    Returns:
        200 → password updated
        400 → invalid or expired token
    """
    data         = request.get_json()
    token_value  = data.get("token",        "").strip() if data else ""
    new_password = data.get("new_password", "").strip() if data else ""

    if not token_value or not new_password:
        return error("Token and new password are required")

    if len(new_password) < 8:
        return error("Password must be at least 8 characters")

    # ── Find token ────────────────────────────────────────────
    token = PasswordResetToken.query.filter_by(token=token_value).first()

    if not token or not token.is_valid():
        return error("Invalid or expired reset token", 400)

    # ── Update password ───────────────────────────────────────
    token.user.password_hash = bcrypt.generate_password_hash(
        new_password
    ).decode("utf-8")

    # ── Mark token as used ────────────────────────────────────
    token.used = True

    db.session.commit()

    return success("Password updated successfully. Please log in.")