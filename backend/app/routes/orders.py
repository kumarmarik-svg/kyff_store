from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import or_
from ..extensions import db
from ..models import (
    Order, OrderItem, Cart, CartItem,
    ProductVariant, Address, ShippingRule, Payment
)

# ── Blueprint ─────────────────────────────────────────────────
orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")


# ── Helpers ───────────────────────────────────────────────────
def error(message, code=400):
    return jsonify({"success": False, "message": message}), code

def success(message, data=None, code=200):
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code


# ── POST /api/orders/place ────────────────────────────────────
@orders_bp.route("/place", methods=["POST"])
@jwt_required()
def place_order():
    """
    Places a new order from current cart.
    This is the most critical route in the entire app.

    Flow:
        1. Validate cart is not empty
        2. Validate shipping address
        3. Calculate shipping charge
        4. Check stock for all items
        5. Create order with address snapshot
        6. Create order items with price snapshots
        7. Reduce stock for each variant
        8. Return order details (cart cleared later on payment success)

    Request body (JSON):
        address_id  : int, use saved address
        OR
        address     : object, use new address directly

        notes       : string, optional delivery instructions

    Returns:
        201 → order placed successfully
        400 → validation error / out of stock
        404 → address not found
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    if not data:
        return error("Request body is required")

    try:
        # ── Get cart ──────────────────────────────────────────
        cart = Cart.query.filter_by(user_id=user_id).first()

        if not cart or cart.is_empty():
            return error("Your cart is empty")

        cart_items = CartItem.query.filter_by(cart_id=cart.id).all()

        if not cart_items:
            return error("Your cart is empty")

        # ── Resolve shipping address ──────────────────────────
        address_id  = data.get("address_id")
        address_obj = data.get("address")

        if address_id:
            # Use saved address
            address = Address.query.filter_by(
                id      = address_id,
                user_id = user_id
            ).first()
            if not address:
                return error("Address not found", 404)

            shipping = {
                "name":    address.full_name,
                "phone":   address.phone,
                "line1":   address.line1,
                "line2":   address.line2,
                "city":    address.city,
                "state":   address.state,
                "pincode": address.pincode,
            }

        elif address_obj:
            # Use inline address from request
            required_fields = ["full_name", "phone", "line1", "city", "state", "pincode"]
            for field in required_fields:
                if not (address_obj.get(field) or "").strip():
                    return error(f"Address field '{field}' is required")

            shipping = {
                "name":    address_obj["full_name"].strip(),
                "phone":   address_obj["phone"].strip(),
                "line1":   address_obj["line1"].strip(),
                "line2":   (address_obj.get("line2") or "").strip() or None,
                "city":    address_obj["city"].strip(),
                "state":   address_obj["state"].strip(),
                "pincode": address_obj["pincode"].strip(),
            }

        else:
            return error("Shipping address is required")

        # ── Validate stock for all items before touching DB ───
        # Check everything BEFORE making any changes so no partial
        # stock reductions happen if one item fails.
        stock_errors = []
        for item in cart_items:
            variant = ProductVariant.query.get(item.variant_id)
            if not variant or not variant.is_active:
                # Safely get a name for the error message without
                # touching item.variant which may also be None.
                label = getattr(variant, "label", None) or f"item #{item.variant_id}"
                stock_errors.append(f"'{label}' is no longer available")
            elif item.quantity > variant.stock_qty:
                product_name = (
                    variant.product.name if variant.product else "product"
                )
                stock_errors.append(
                    f"Only {variant.stock_qty} units available "
                    f"for '{product_name} — {variant.label}'"
                )

        if stock_errors:
            return error(" | ".join(stock_errors))

        # ── Calculate totals ──────────────────────────────────
        subtotal = round(
            sum(
                float(ProductVariant.query.get(item.variant_id).effective_price())
                * item.quantity
                for item in cart_items
            ), 2
        )

        shipping_charge = ShippingRule.get_charge_for(subtotal)
        total           = round(subtotal + shipping_charge, 2)

        # ── Create order ──────────────────────────────────────
        order = Order(
            user_id             = user_id,
            order_number        = Order.generate_order_number(),
            shipping_name       = shipping["name"],
            shipping_phone      = shipping["phone"],
            shipping_line1      = shipping["line1"],
            shipping_line2      = shipping["line2"],
            shipping_city       = shipping["city"],
            shipping_state      = shipping["state"],
            shipping_pincode    = shipping["pincode"],
            subtotal            = subtotal,
            shipping_charge     = shipping_charge,
            discount_amount     = 0.00,
            total               = total,
            status              = "pending",
            notes               = (data.get("notes") or "").strip() or None,
            # Payment must be completed within 15 minutes
            payment_expires_at  = datetime.utcnow() + timedelta(minutes=15),
        )
        db.session.add(order)
        db.session.flush()   # gets order.id before final commit

        # ── Create order items + reduce stock ─────────────────
        for item in cart_items:
            variant    = ProductVariant.query.get(item.variant_id)
            order_item = OrderItem.build_from_cart_item(item, order.id)
            db.session.add(order_item)
            variant.reduce_stock(item.quantity)

        db.session.commit()

        return success(
            message = "Order placed successfully",
            data    = {"order": order.to_dict(include_items=True)},
            code    = 201
        )

    except Exception as e:
        db.session.rollback()
        # Log the real error server-side for debugging while returning
        # a safe JSON response so the frontend never sees a 500 HTML page.
        import traceback
        traceback.print_exc()
        return error(f"Could not place order: {str(e)}", 500)


# ── GET /api/orders ───────────────────────────────────────────
@orders_bp.route("/", methods=["GET"])
@jwt_required()
def list_orders():
    """
    Returns all orders for the logged-in user, newest first.

    Query params:
        status → filter by order status (optional)

    Design rules:
        • Never touches payments table in the main query — avoids N+1
          and survives if payments table has schema issues.
        • Reads payment_status via a single per-order query wrapped in
          try/except so a missing payments row never crashes the list.
        • Accesses payment_expires_at defensively (getattr) in case the
          migration adding that column hasn't been applied yet.
        • Every per-order serialisation is individually try/excepted —
          one broken order never kills the whole response.
        • Always returns HTTP 200, even for zero orders.

    Returns:
        200 → {"success": true, "data": {"orders": [...]}}
    """
    user_id = int(get_jwt_identity())
    status  = request.args.get("status", None)

    # ── Fetch orders — no JOIN to payments ────────────────────
    try:
        query = Order.query.filter(Order.user_id == user_id)

        if status:
            query = query.filter(Order.status == status)

            # For the pending tab exclude expired payment windows at
            # the SQL level, but guard against missing column.
            if status == "pending":
                try:
                    query = query.filter(
                        or_(
                            Order.payment_expires_at == None,   # noqa: E711
                            Order.payment_expires_at > datetime.utcnow()
                        )
                    )
                except Exception:
                    pass  # column not yet in DB — skip the filter safely

        orders = query.order_by(Order.created_at.desc()).all()

    except Exception:
        import traceback
        traceback.print_exc()
        # Return empty list — never a 500 — so the frontend can
        # display "no orders" instead of a crash page.
        return jsonify({
            "success": True,
            "message": "Orders fetched",
            "data":    {"orders": []}
        }), 200

    # ── Serialise each order safely ───────────────────────────
    result = []
    for order in orders:
        try:
            # Payment status — one query per order, but ONLY if needed.
            # Falls back to "pending" if the payment row is missing.
            try:
                payment = Payment.query.filter_by(order_id=order.id)\
                    .order_by(Payment.created_at.desc()).first()
                payment_status  = payment.status  if payment else "pending"
                payment_gateway = payment.gateway if payment else None
            except Exception:
                payment_status  = "pending"
                payment_gateway = None

            # Items — snapshot fields only, no JOINs to live product data.
            items = []
            try:
                order_items = OrderItem.query.filter_by(order_id=order.id).all()
                for oi in order_items:
                    image_url = None
                    try:
                        if oi.variant and oi.variant.product:
                            img = oi.variant.product.images\
                                .filter_by(is_primary=True).first() \
                                or oi.variant.product.images.first()
                            image_url = img.image_url if img else None
                    except Exception:
                        pass

                    items.append({
                        "id":            oi.id,
                        "variant_id":    oi.variant_id,
                        "product_name":  oi.product_name  or "",
                        "variant_label": oi.variant_label or "",
                        "quantity":      oi.quantity,
                        "unit_price":    float(oi.unit_price),
                        "line_total":    float(oi.line_total),
                        "image_url":     image_url,
                    })
            except Exception:
                items = []

            # payment_expires_at — column may not exist if migration
            # hasn't been applied; use getattr with None default.
            expires_at = getattr(order, "payment_expires_at", None)
            is_expired = False
            if expires_at and order.status == "pending":
                is_expired = datetime.utcnow() > expires_at

            result.append({
                "id":                 order.id,
                "order_number":       order.order_number,
                "status":             order.status,
                "subtotal":           float(order.subtotal),
                "shipping_charge":    float(order.shipping_charge),
                "discount_amount":    float(order.discount_amount),
                "total":              float(order.total),
                "payment_status":     payment_status,
                "payment_gateway":    payment_gateway,
                "payment_expires_at": expires_at.isoformat() if expires_at else None,
                "is_payment_expired": is_expired,
                "is_paid":            payment_status == "success",
                "is_cancellable":     order.status in (
                                          "pending", "confirmed", "processing"
                                      ),
                "notes":              order.notes,
                "created_at":         order.created_at.isoformat(),
                "items":              items,
            })

        except Exception:
            # Skip a single broken order — do not crash the whole list
            import traceback
            traceback.print_exc()
            continue

    return jsonify({
        "success": True,
        "message": "Orders fetched",
        "data":    {"orders": result}
    }), 200


# ── GET /api/orders/<order_number> ────────────────────────────
@orders_bp.route("/<order_number>", methods=["GET"])
@jwt_required()
def get_order(order_number):
    """
    Returns full order detail by order number.
    Includes all items, payment status, shipping address.

    URL param:
        order_number → e.g. KYFF-20240315-A3F9B2

    Returns:
        200 → full order detail
        403 → order belongs to another user
        404 → order not found
    """
    user_id = int(get_jwt_identity())

    order = Order.query.filter_by(order_number=order_number).first()

    if not order:
        return error("Order not found", 404)

    # ── Ownership check ───────────────────────────────────────
    # Never let user A see user B's order
    if order.user_id != user_id:
        return error("You do not have access to this order", 403)

    # Auto-expire if payment window has elapsed
    if order.expire_if_needed():
        db.session.commit()

    return success(
        message = "Order fetched",
        data    = {"order": order.to_dict(include_items=True)}
    )


# ── POST /api/orders/<order_number>/cancel ────────────────────
@orders_bp.route("/<order_number>/cancel", methods=["POST"])
@jwt_required()
def cancel_order(order_number):
    """
    Cancels an order if it hasn't been shipped yet.
    Restores stock for all items automatically.

    URL param:
        order_number → e.g. KYFF-20240315-A3F9B2

    Returns:
        200 → order cancelled
        400 → order cannot be cancelled (already shipped)
        403 → order belongs to another user
        404 → order not found
    """
    user_id = int(get_jwt_identity())

    order = Order.query.filter_by(order_number=order_number).first()

    if not order:
        return error("Order not found", 404)

    if order.user_id != user_id:
        return error("You do not have access to this order", 403)

    # cancel() raises ValueError if not cancellable
    try:
        order.cancel()
        db.session.commit()
    except ValueError as e:
        return error(str(e))

    return success(
        message = "Order cancelled successfully",
        data    = {"order": order.to_dict(include_items=True)}
    )


# ── GET /api/orders/<order_number>/track ──────────────────────
@orders_bp.route("/<order_number>/track", methods=["GET"])
@jwt_required()
def track_order(order_number):
    """
    Returns order status and tracking timeline.
    Used for the order tracking page.

    Returns:
        200 → order status + timeline
        403 → not your order
        404 → not found
    """
    user_id = int(get_jwt_identity())

    order = Order.query.filter_by(order_number=order_number).first()

    if not order:
        return error("Order not found", 404)

    if order.user_id != user_id:
        return error("You do not have access to this order", 403)

    # ── Build status timeline ─────────────────────────────────
    all_statuses = [
        "pending",
        "confirmed",
        "processing",
        "shipped",
        "delivered"
    ]

    # Mark each step as completed, current, or upcoming
    timeline = []
    for s in all_statuses:
        if order.status == "cancelled":
            timeline.append({"status": s, "state": "cancelled"})
        elif all_statuses.index(s) < all_statuses.index(order.status):
            timeline.append({"status": s, "state": "completed"})
        elif s == order.status:
            timeline.append({"status": s, "state": "current"})
        else:
            timeline.append({"status": s, "state": "upcoming"})

    return success(
        message = "Order tracking fetched",
        data    = {
            "order_number": order.order_number,
            "status":       order.status,
            "is_paid":      order.is_paid(),
            "timeline":     timeline,
            "created_at":   order.created_at.isoformat(),
        }
    )