from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Address
from ..utils.responses import error, success

# ── Blueprint ─────────────────────────────────────────────────
addresses_bp = Blueprint("addresses", __name__, url_prefix="/api/addresses")


# ── GET /api/addresses ────────────────────────────────────────
@addresses_bp.route("/", methods=["GET"])
@jwt_required()
def list_addresses():
    """
    Returns all saved addresses for the logged-in user.

    Ordering: default address first, then by creation date ascending.
    The frontend uses is_default to pre-select the delivery address
    on the checkout page (Amazon/Flipkart style).

    Returns:
        200 → {"addresses": [...]}
    """
    user_id = int(get_jwt_identity())

    addresses = (
        Address.query
        .filter_by(user_id=user_id)
        .order_by(Address.is_default.desc(), Address.created_at.asc())
        .all()
    )

    return success(
        message = "Addresses fetched",
        data    = {"addresses": [a.to_dict() for a in addresses]}
    )


# ── POST /api/addresses ───────────────────────────────────────
@addresses_bp.route("/", methods=["POST"])
@jwt_required()
def add_address():
    """
    Adds a new address for the logged-in user.

    Deduplication:
        If an address with the same (phone, line1, city, pincode)
        already exists for this user, it is returned as-is — no
        duplicate row is inserted.

    Request body (JSON):
        full_name   : string, required
        phone       : string, required
        line1       : string, required
        line2       : string, optional
        city        : string, required
        state       : string, required
        pincode     : string, required
        set_default : bool,   optional (default false)

    Default address rules:
        • First address saved → automatically becomes default.
        • set_default=true    → clears existing default, sets this one.
        • Otherwise           → is_default=false.

    Returns:
        201 → address created
        200 → duplicate found, existing address returned
        400 → validation error
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    if not data:
        return error("Request body is required")

    required_fields = ["full_name", "phone", "line1", "city", "state", "pincode"]
    for field in required_fields:
        if not (data.get(field) or "").strip():
            return error(f"'{field}' is required")

    full_name = data["full_name"].strip()
    phone     = data["phone"].strip()
    line1     = data["line1"].strip()
    line2     = (data.get("line2") or "").strip() or None
    city      = data["city"].strip()
    state     = data["state"].strip()
    pincode   = data["pincode"].strip()
    set_def   = bool(data.get("set_default"))

    # ── Deduplication check ───────────────────────────────────
    existing = Address.query.filter_by(
        user_id = user_id,
        phone   = phone,
        line1   = line1,
        city    = city,
        pincode = pincode,
    ).first()

    if existing:
        # Honor set_default even on an existing address
        if set_def and not existing.is_default:
            existing.set_as_default()
            db.session.commit()
        return success(
            message = "Address already exists",
            data    = {"address": existing.to_dict()},
            code    = 200,
        )

    # ── Determine default flag ────────────────────────────────
    is_first = Address.query.filter_by(user_id=user_id).count() == 0

    if set_def or is_first:
        # Clear existing default — only one allowed per user
        Address.query.filter_by(user_id=user_id).update({"is_default": False})
        is_default = True
    else:
        is_default = False

    # ── Insert ────────────────────────────────────────────────
    address = Address(
        user_id    = user_id,
        full_name  = full_name,
        phone      = phone,
        line1      = line1,
        line2      = line2,
        city       = city,
        state      = state,
        pincode    = pincode,
        is_default = is_default,
    )
    db.session.add(address)
    db.session.commit()

    return success(
        message = "Address added",
        data    = {"address": address.to_dict()},
        code    = 201,
    )


# ── PATCH /api/addresses/<id>/set-default ─────────────────────
@addresses_bp.route("/<int:address_id>/set-default", methods=["PATCH"])
@jwt_required()
def set_default_address(address_id):
    """
    Makes an address the user's default delivery address.

    Clears is_default on all other addresses for this user so the
    single-default constraint is always maintained.

    Returns:
        200 → default updated
        404 → address not found / not owned by user
    """
    user_id = int(get_jwt_identity())

    address = Address.query.filter_by(
        id      = address_id,
        user_id = user_id
    ).first()

    if not address:
        return error("Address not found", 404)

    if address.is_default:
        return success(
            message = "Already the default address",
            data    = {"address": address.to_dict()}
        )

    address.set_as_default()
    db.session.commit()

    return success(
        message = "Default address updated",
        data    = {"address": address.to_dict()}
    )


# ── DELETE /api/addresses/<id> ────────────────────────────────
@addresses_bp.route("/<int:address_id>", methods=["DELETE"])
@jwt_required()
def delete_address(address_id):
    """
    Deletes a saved address.

    Default address deletion:
        If the address being deleted is the current default AND the user
        has other addresses, the oldest remaining address is automatically
        promoted to default (same behaviour as Amazon).
        If it is the user's only address, deletion is blocked — the user
        cannot be left with no addresses and an implicit broken default.

    Returns:
        200 → deleted (with promoted address info if default was deleted)
        400 → cannot delete only address
        404 → address not found / not owned by user
    """
    user_id = int(get_jwt_identity())

    address = Address.query.filter_by(
        id      = address_id,
        user_id = user_id
    ).first()

    if not address:
        return error("Address not found", 404)

    promoted = None

    if address.is_default:
        # Find the next oldest address to auto-promote
        other = (
            Address.query
            .filter(
                Address.user_id == user_id,
                Address.id      != address_id
            )
            .order_by(Address.created_at.asc())
            .first()
        )

        if not other:
            return error(
                "Cannot delete your only saved address. "
                "Add another address first.",
                400
            )

        other.is_default = True
        promoted = other

    db.session.delete(address)
    db.session.commit()

    response_data = {}
    if promoted:
        response_data["new_default"] = promoted.to_dict()

    return success(
        message = "Address deleted"
            + (" — default reassigned" if promoted else ""),
        data    = response_data or None
    )
