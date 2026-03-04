from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import (
    Order, OrderItem, Cart, CartItem,
    ProductVariant, Address, ShippingRule
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
        8. Clear cart
        9. Return order details

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

    # ── Get cart ──────────────────────────────────────────────
    cart = Cart.query.filter_by(user_id=user_id).first()

    if not cart or cart.is_empty():
        return error("Your cart is empty")

    cart_items = CartItem.query.filter_by(cart_id=cart.id).all()

    # ── Resolve shipping address ──────────────────────────────
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
            if not address_obj.get(field, "").strip():
                return error(f"Address field '{field}' is required")

        shipping = {
            "name":    address_obj["full_name"].strip(),
            "phone":   address_obj["phone"].strip(),
            "line1":   address_obj["line1"].strip(),
            "line2":   address_obj.get("line2", "").strip() or None,
            "city":    address_obj["city"].strip(),
            "state":   address_obj["state"].strip(),
            "pincode": address_obj["pincode"].strip(),
        }

    else:
        return error("Shipping address is required")

    # ── Validate stock for all items before touching DB ───────
    # Check everything BEFORE making any changes.
    # If item 3 of 5 is out of stock, we don't want
    # items 1 and 2 already reduced.
    stock_errors = []
    for item in cart_items:
        variant = ProductVariant.query.get(item.variant_id)
        if not variant or not variant.is_active:
            stock_errors.append(
                f"'{item.variant.product.name}' is no longer available"
            )
        elif item.quantity > variant.stock_qty:
            stock_errors.append(
                f"Only {variant.stock_qty} units available "
                f"for '{variant.product.name} {variant.label}'"
            )

    if stock_errors:
        return error(" | ".join(stock_errors))

    # ── Calculate totals ──────────────────────────────────────
    subtotal = round(
        sum(
            float(ProductVariant.query.get(item.variant_id).effective_price())
            * item.quantity
            for item in cart_items
        ), 2
    )

    shipping_charge = ShippingRule.get_charge_for(subtotal)
    total           = round(subtotal + shipping_charge, 2)

    # ── Create order ──────────────────────────────────────────
    order = Order(
        user_id          = user_id,
        order_number     = Order.generate_order_number(),
        shipping_name    = shipping["name"],
        shipping_phone   = shipping["phone"],
        shipping_line1   = shipping["line1"],
        shipping_line2   = shipping["line2"],
        shipping_city    = shipping["city"],
        shipping_state   = shipping["state"],
        shipping_pincode = shipping["pincode"],
        subtotal         = subtotal,
        shipping_charge  = shipping_charge,
        discount_amount  = 0.00,
        total            = total,
        status           = "pending",
        notes            = data.get("notes", "").strip() or None
    )
    db.session.add(order)
    db.session.flush()   # gets order.id before final commit

    # ── Create order items + reduce stock ─────────────────────
    for item in cart_items:
        variant    = ProductVariant.query.get(item.variant_id)
        order_item = OrderItem.build_from_cart_item(item, order.id)
        db.session.add(order_item)
        variant.reduce_stock(item.quantity)

    # ── Clear cart ────────────────────────────────────────────
    for item in cart_items:
        db.session.delete(item)

    db.session.commit()

    return success(
        message = "Order placed successfully",
        data    = {"order": order.to_dict(include_items=True)},
        code    = 201
    )


# ── GET /api/orders ───────────────────────────────────────────
@orders_bp.route("/", methods=["GET"])
@jwt_required()
def list_orders():
    """
    Returns paginated order history for logged-in user.

    Query params:
        page     → page number (default 1)
        per_page → orders per page (default 10)
        status   → filter by status (optional)

    Returns:
        200 → list of orders with pagination
    """
    user_id  = int(get_jwt_identity())
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 10, type=int)
    status   = request.args.get("status",   None)

    query = Order.query.filter_by(user_id=user_id)

    if status:
        query = query.filter_by(status=status)

    paginated = (
        query
        .order_by(Order.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return success(
        message = "Orders fetched",
        data    = {
            "orders": [o.to_dict() for o in paginated.items],
            "pagination": {
                "page":        paginated.page,
                "per_page":    paginated.per_page,
                "total":       paginated.total,
                "total_pages": paginated.pages,
                "has_next":    paginated.has_next,
                "has_prev":    paginated.has_prev,
            }
        }
    )


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