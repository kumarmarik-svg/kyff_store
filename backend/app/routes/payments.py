from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from ..extensions import db
from ..models import Order, Payment, Cart, CartItem, OrderItem, ProductVariant
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
    Raises ValueError if credentials are not configured.
    """
    key_id     = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")

    if not key_id or not key_secret:
        raise ValueError(
            "Razorpay credentials are not configured. "
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env"
        )

    import razorpay
    return razorpay.Client(auth=(key_id, key_secret))


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

    if order.status == "expired":
        return error("This order has expired and can no longer be paid")

    if order.is_paid():
        return error("This order is already paid")

    # ── Prevent duplicate Razorpay order creation ──────────────
    # If an initiated payment already exists for this order, return it
    # so the frontend can resume the same Razorpay checkout session.
    existing_payment = Payment.query.filter_by(
        order_id = order.id,
        status   = "initiated"
    ).first()

    if existing_payment and existing_payment.gateway_order_id:
        return success(
            message = "Payment already initiated — resuming existing session",
            data    = {
                "razorpay_order_id": existing_payment.gateway_order_id,
                "key_id":            os.getenv("RAZORPAY_KEY_ID"),
                "amount":            int(float(order.total) * 100),
                "currency":          "INR",
                "order_number":      order.order_number,
                "payment_id":        existing_payment.id,
            }
        )

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
            "key_id":            os.getenv("RAZORPAY_KEY_ID"),
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
        order = payment.order
        payment.mark_success(
            transaction_id   = rz_payment_id,
            gateway_response = data
        )
        order.status = "confirmed"

        # ── Cancel other pending/payment_failed orders for this user ──
        # Stock is restored for those orders so items are back on sale.
        stale_orders = Order.query.filter(
            Order.user_id == user_id,
            Order.id      != order.id,
            Order.status.in_(["pending", "payment_failed"])
        ).all()
        for stale in stale_orders:
            for item in OrderItem.query.filter_by(order_id=stale.id).all():
                if item.variant_id:
                    variant = ProductVariant.query.get(item.variant_id)
                    if variant:
                        variant.restore_stock(item.quantity)
            stale.status = "cancelled"

        # ── Clear cart on successful payment ──────────────────
        cart = Cart.query.filter_by(user_id=user_id).first()
        if cart:
            CartItem.query.filter_by(cart_id=cart.id).delete()

        db.session.commit()

        return success(
            message = "Payment verified successfully",
            data    = {
                "order":   order.to_dict(include_items=True),
                "payment": payment.to_dict()
            }
        )

    # ── Signature mismatch → possible tampering ───────────────
    else:
        payment.mark_failed(gateway_response=data)
        # Mark order as payment_failed but do NOT restore stock.
        # The user may retry immediately; restoring stock risks another
        # buyer purchasing the same item before the retry completes.
        # Stock is only restored on order expiry or explicit cancellation.
        payment.order.status = "payment_failed"
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
            order = payment.order
            payment.mark_success(
                transaction_id   = rz_payment_id,
                gateway_response = event
            )
            order.status = "confirmed"

            # Cancel any other pending/payment_failed orders for this user
            # and restore their stock so those items go back on sale.
            if order.user_id:
                stale_orders = Order.query.filter(
                    Order.user_id == order.user_id,
                    Order.id      != order.id,
                    Order.status.in_(["pending", "payment_failed"])
                ).all()
                for stale in stale_orders:
                    for item in OrderItem.query.filter_by(order_id=stale.id).all():
                        if item.variant_id:
                            variant = ProductVariant.query.get(item.variant_id)
                            if variant:
                                variant.restore_stock(item.quantity)
                    stale.status = "cancelled"

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
            order = payment.order
            if order and order.status in ("pending", "payment_failed"):
                # Mark failed but do NOT restore stock — user may retry.
                # Stock is only released on expiry or cancellation.
                order.status = "payment_failed"
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
    # COD orders are immediately confirmed — no gateway verification step,
    # so the payment goes straight to 'success'.
    payment = Payment(
        order_id = order.id,
        gateway  = "cod",
        amount   = order.total,
        currency = "INR",
        status   = "success",
        paid_at  = datetime.utcnow()
    )
    db.session.add(payment)

    order.status = "confirmed"

    # ── Clear cart on COD confirmation ────────────────────────
    cart = Cart.query.filter_by(user_id=user_id).first()
    if cart:
        CartItem.query.filter_by(cart_id=cart.id).delete()

    db.session.commit()

    return success(
        message = "COD order confirmed",
        data    = {
            "order":   order.to_dict(include_items=True),
            "payment": payment.to_dict()
        }
    )


# ── POST /api/payments/retry/<order_number> ───────────────────
@payments_bp.route("/retry/<order_number>", methods=["POST"])
@jwt_required()
def retry_payment(order_number):
    """
    Creates a new Razorpay order for an existing unpaid order.
    Called when the user clicks "Pay Now / Retry Payment".

    Rules:
        - Order must belong to the logged-in user
        - Order status must be 'pending' or 'payment_failed'
        - Order must not be payment-expired
        - Reuses the existing 'initiated' payment record if one exists;
          creates a new row only when the previous attempt was 'failed'.

    Returns:
        200 → new Razorpay order details for frontend checkout
        400 → order not in a retryable state
        404 → order not found
    """
    user_id = int(get_jwt_identity())

    order = Order.query.filter_by(
        order_number = order_number,
        user_id      = user_id
    ).first()

    if not order:
        return error("Order not found", 404)

    if order.status == "confirmed":
        return error("This order is already paid and confirmed")

    if order.status == "cancelled":
        return error("Cancelled orders cannot be retried")

    if order.status == "expired":
        return error("This order has expired and cannot be retried")

    if order.status not in ("pending", "payment_failed"):
        return error(f"Cannot retry payment for order with status '{order.status}'")

    if order.is_payment_expired():
        # Window elapsed — expire the order and restore stock now
        order.expire_if_needed()
        db.session.commit()
        return error("Payment window has expired. This order has been marked as expired.")

    if order.is_paid():
        return error("This order is already paid")

    # ── payment_failed retry: stock is still reserved, reset window ──
    # Do NOT reduce stock again — the original reduction from place_order
    # is still in effect. Just give the user a fresh 15-minute window.
    if order.status == "payment_failed":
        order.payment_expires_at = datetime.utcnow() + timedelta(minutes=15)
        order.status = "pending"

    # ── Create new Razorpay order ──────────────────────────────
    amount_paise = int(float(order.total) * 100)

    try:
        client   = get_razorpay_client()
        rz_order = client.order.create({
            "amount":   amount_paise,
            "currency": "INR",
            "receipt":  order.order_number,
            "notes": {
                "order_number": order.order_number,
                "user_id":      str(user_id),
                "retry":        "true"
            }
        })
    except Exception as e:
        return error(f"Payment gateway error: {str(e)}", 502)

    # ── Reuse existing initiated payment record if available ───
    # A previous attempt that never reached verify (user closed popup)
    # leaves an 'initiated' payment row. Reuse it with the new Razorpay
    # order ID so verify_payment() can find it correctly.
    # If the previous attempt was marked 'failed' (webhook), create fresh.
    existing_payment = Payment.query.filter_by(
        order_id = order.id,
        status   = "initiated"
    ).first()

    if existing_payment:
        existing_payment.gateway_order_id = rz_order["id"]
        payment = existing_payment
    else:
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
            "key_id":            os.getenv("RAZORPAY_KEY_ID"),
            "amount":            amount_paise,
            "currency":          "INR",
            "order_number":      order.order_number,
            "payment_id":        payment.id,
            "payment_expires_at": order.payment_expires_at.isoformat()
                                  if order.payment_expires_at else None,
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