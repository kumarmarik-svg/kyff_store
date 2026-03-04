from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Order, Payment
import hmac
import hashlib
import os

# ── Blueprint ─────────────────────────────────────────────────
payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


# ── Razorpay Client — lazy import ────────────────────────────
def get_razorpay_client():
    """
    Imports razorpay inside function to avoid startup errors.
    Only loads when a payment route is actually called.
    """
    import razorpay
    return razorpay.Client(
        auth=(
            os.getenv("RAZORPAY_KEY_ID"),
            os.getenv("RAZORPAY_KEY_SECRET")
        )
    )


# ── Helpers ───────────────────────────────────────────────────
def error(message, code=400):
    return jsonify({"success": False, "message": message}), code

def success(message, data=None, code=200):
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code


# ── POST /api/payments/initiate ───────────────────────────────
@payments_bp.route("/initiate", methods=["POST"])
@jwt_required()
def initiate_payment():
    """
    Creates a Razorpay order and payment record.
    Called after order is placed, before customer pays.

    Flow:
        1. Find the pending order
        2. Create Razorpay order via API
        3. Create Payment record in DB (status: initiated)
        4. Return Razorpay order details to frontend
        5. Frontend opens Razorpay checkout popup

    Request body (JSON):
        order_number : string, required

    Returns:
        200 → razorpay order details for frontend checkout
        400 → order already paid or invalid
        404 → order not found
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    order_number = data.get("order_number") if data else None
    if not order_number:
        return error("order_number is required")

    # ── Find order ────────────────────────────────────────────
    order = Order.query.filter_by(
        order_number = order_number,
        user_id      = user_id
    ).first()

    if not order:
        return error("Order not found", 404)

    if order.status == "cancelled":
        return error("Cannot initiate payment for a cancelled order")

    if order.is_paid():
        return error("This order is already paid")

    # ── Create Razorpay order ─────────────────────────────────
    # Razorpay requires amount in PAISE (1 rupee = 100 paise)
    amount_paise = int(float(order.total) * 100)

    try:
        client   = get_razorpay_client()
        rz_order = client.order.create({
            "amount":   amount_paise,
            "currency": "INR",
            "receipt":  order.order_number,
            "notes": {
                "order_number": order.order_number,
                "user_id":      str(user_id)
            }
        })
    except Exception as e:
        return error(f"Payment gateway error: {str(e)}", 502)

    # ── Save payment record ───────────────────────────────────
    payment = Payment.initiate(
        order_id         = order.id,
        gateway          = "razorpay",
        amount           = order.total,
        gateway_order_id = rz_order["id"]
    )
    db.session.add(payment)
    db.session.commit()

    return success(
        message = "Payment initiated",
        data    = {
            "razorpay_order_id": rz_order["id"],
            "razorpay_key_id":   os.getenv("RAZORPAY_KEY_ID"),
            "amount":            amount_paise,
            "currency":          "INR",
            "order_number":      order.order_number,
            "payment_id":        payment.id,
        }
    )


# ── POST /api/payments/verify ─────────────────────────────────
@payments_bp.route("/verify", methods=["POST"])
@jwt_required()
def verify_payment():
    """
    Verifies Razorpay payment signature after customer pays.
    Called by frontend immediately after Razorpay popup closes.

    Request body (JSON):
        razorpay_order_id   : string, required
        razorpay_payment_id : string, required
        razorpay_signature  : string, required
        payment_id          : int,    required

    Returns:
        200 → payment verified, order confirmed
        400 → signature mismatch
        404 → payment record not found
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    rz_order_id   = data.get("razorpay_order_id")
    rz_payment_id = data.get("razorpay_payment_id")
    rz_signature  = data.get("razorpay_signature")
    payment_id    = data.get("payment_id")

    if not all([rz_order_id, rz_payment_id, rz_signature, payment_id]):
        return error("All payment verification fields are required")

    # ── Find payment record ───────────────────────────────────
    payment = Payment.query.filter_by(
        id               = payment_id,
        gateway_order_id = rz_order_id
    ).first()

    if not payment:
        return error("Payment record not found", 404)

    # ── Verify signature ──────────────────────────────────────
    key      = os.getenv("RAZORPAY_KEY_SECRET", "").encode("utf-8")
    message  = f"{rz_order_id}|{rz_payment_id}".encode("utf-8")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()

    # ── Signature match → payment genuine ─────────────────────
    if hmac.compare_digest(expected, rz_signature):
        payment.mark_success(
            transaction_id   = rz_payment_id,
            gateway_response = data
        )
        payment.order.status = "confirmed"
        db.session.commit()

        return success(
            message = "Payment verified successfully",
            data    = {
                "order":   payment.order.to_dict(include_items=True),
                "payment": payment.to_dict()
            }
        )

    # ── Signature mismatch → possible tampering ───────────────
    else:
        payment.mark_failed(gateway_response=data)
        db.session.commit()
        return error("Payment verification failed. Please contact support.", 400)


# ── POST /api/payments/webhook ────────────────────────────────
@payments_bp.route("/webhook", methods=["POST"])
def razorpay_webhook():
    """
    Handles Razorpay webhook events.
    Called directly by Razorpay servers — NOT by frontend.
    No JWT auth — Razorpay doesn't send tokens.
    Always returns 200 so Razorpay doesn't retry.
    """
    payload   = request.get_data(as_text=True)
    signature = request.headers.get("X-Razorpay-Signature", "")

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").encode("utf-8")
    expected       = hmac.new(
        webhook_secret,
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return jsonify({"status": "invalid signature"}), 200

    event      = request.get_json(force=True)
    event_type = event.get("event")

    # ── payment.captured ──────────────────────────────────────
    if event_type == "payment.captured":
        payment_entity = event["payload"]["payment"]["entity"]
        rz_order_id    = payment_entity.get("order_id")
        rz_payment_id  = payment_entity.get("id")

        payment = Payment.query.filter_by(
            gateway_order_id=rz_order_id
        ).first()

        if payment and not payment.is_successful():
            payment.mark_success(
                transaction_id   = rz_payment_id,
                gateway_response = event
            )
            payment.order.status = "confirmed"
            db.session.commit()

    # ── payment.failed ────────────────────────────────────────
    elif event_type == "payment.failed":
        payment_entity = event["payload"]["payment"]["entity"]
        rz_order_id    = payment_entity.get("order_id")

        payment = Payment.query.filter_by(
            gateway_order_id=rz_order_id
        ).first()

        if payment and not payment.is_successful():
            payment.mark_failed(gateway_response=event)
            db.session.commit()

    return jsonify({"status": "ok"}), 200


# ── POST /api/payments/cod ────────────────────────────────────
@payments_bp.route("/cod", methods=["POST"])
@jwt_required()
def cash_on_delivery():
    """
    Confirms a Cash on Delivery order.
    No gateway — just creates a COD payment record.

    Request body (JSON):
        order_number : string, required
    """
    user_id      = int(get_jwt_identity())
    data         = request.get_json()
    order_number = data.get("order_number") if data else None

    if not order_number:
        return error("order_number is required")

    order = Order.query.filter_by(
        order_number = order_number,
        user_id      = user_id
    ).first()

    if not order:
        return error("Order not found", 404)

    if order.is_paid():
        return error("This order is already paid")

    if order.status == "cancelled":
        return error("Cannot confirm a cancelled order")

    # ── Create COD payment record ─────────────────────────────
    payment = Payment(
        order_id = order.id,
        gateway  = "cod",
        amount   = order.total,
        currency = "INR",
        status   = "pending"
    )
    db.session.add(payment)

    order.status = "confirmed"
    db.session.commit()

    return success(
        message = "COD order confirmed",
        data    = {
            "order":   order.to_dict(include_items=True),
            "payment": payment.to_dict()
        }
    )


# ── GET /api/payments/<order_number> ──────────────────────────
@payments_bp.route("/<order_number>", methods=["GET"])
@jwt_required()
def get_payment_status(order_number):
    """
    Returns payment status for an order.

    Returns:
        200 → payment status
        403 → not your order
        404 → order not found
    """
    user_id = int(get_jwt_identity())

    order = Order.query.filter_by(order_number=order_number).first()

    if not order:
        return error("Order not found", 404)

    if order.user_id != user_id:
        return error("You do not have access to this order", 403)

    payments = order.payments.order_by(Payment.created_at.desc()).all()

    return success(
        message = "Payment status fetched",
        data    = {
            "order_number": order.order_number,
            "order_status": order.status,
            "is_paid":      order.is_paid(),
            "payments":     [p.to_dict() for p in payments]
        }
    )