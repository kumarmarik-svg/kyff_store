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


def _address_to_shipping(address):
    """Converts a saved Address row into the order shipping snapshot dict."""
    return {
        "name":    address.full_name,
        "phone":   address.phone,
        "line1":   address.line1,
        "line2":   address.line2,
        "city":    address.city,
        "state":   address.state,
        "pincode": address.pincode,
    }


def _resolve_shipping_address(user_id, data):
    """
    Resolves the shipping address for an order from the request body.

    Resolution priority:
        1. address_id  → load saved address by primary key
        2. address obj → deduplicate on (phone, line1, city, pincode);
                         optionally save if save_address=true
        3. (neither)   → fall back to the user's default address

    Top-level request flags (read from the root of the JSON body):
        save_address : bool — persist a new inline address to the DB
        set_default  : bool — make the saved address the new default

    Returns:
        (shipping_dict, None)          on success
        (None,          error_response) on failure — return it from the route
    """
    address_id  = data.get("address_id")
    address_obj = data.get("address")
    save        = bool(data.get("save_address"))
    set_def     = bool(data.get("set_default"))

    # ── 1. Saved address by ID ────────────────────────────────
    if address_id:
        address = Address.query.filter_by(
            id      = address_id,
            user_id = user_id
        ).first()
        if not address:
            return None, error("Address not found", 404)
        return _address_to_shipping(address), None

    # ── 2. Inline address object ──────────────────────────────
    if address_obj:
        required_fields = ["full_name", "phone", "line1", "city", "state", "pincode"]
        for field in required_fields:
            if not (address_obj.get(field) or "").strip():
                return None, error(f"Address field '{field}' is required")

        full_name = address_obj["full_name"].strip()
        phone     = address_obj["phone"].strip()
        line1     = address_obj["line1"].strip()
        line2     = (address_obj.get("line2") or "").strip() or None
        city      = address_obj["city"].strip()
        state     = address_obj["state"].strip()
        pincode   = address_obj["pincode"].strip()

        # Deduplicate: if this address already exists for the user,
        # reuse it — no insert, no duplicate row.
        existing = Address.query.filter_by(
            user_id = user_id,
            phone   = phone,
            line1   = line1,
            city    = city,
            pincode = pincode,
        ).first()

        if existing:
            return _address_to_shipping(existing), None

        # New address — optionally persist to the addresses table.
        if save:
            is_first = Address.query.filter_by(user_id=user_id).count() == 0

            if set_def or is_first:
                # Clear any existing default before setting the new one.
                # A user must have at most one default address.
                Address.query.filter_by(user_id=user_id).update({"is_default": False})
                is_default = True
            else:
                is_default = False

            new_address = Address(
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
            db.session.add(new_address)
            # flush so the row gets an id; the caller commits with the order
            db.session.flush()

        return {
            "name":    full_name,
            "phone":   phone,
            "line1":   line1,
            "line2":   line2,
            "city":    city,
            "state":   state,
            "pincode": pincode,
        }, None

    # ── 3. Fall back to default address ──────────────────────
    default_address = Address.query.filter_by(
        user_id    = user_id,
        is_default = True
    ).first()

    if not default_address:
        return None, error("Shipping address is required")

    return _address_to_shipping(default_address), None


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
        address_id   : int    — use a saved address by ID
        OR
        address      : object — inline address fields:
                         full_name, phone, line1, [line2],
                         city, state, pincode
        save_address : bool   — persist the inline address (default false)
        set_default  : bool   — make it the user's new default (default false)
        notes        : string — optional delivery instructions

    Address resolution priority:
        1. address_id  → load saved address
        2. address obj → deduplicate; save if save_address=true
        3. (neither)   → use the user's default address

    Returns:
        201 → order placed successfully
        400 → validation error / out of stock
        404 → address not found
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    if not data:
        return error("Request body is required")

    # ── Block duplicate active orders ──────────────────────────
    # Prevent a user from stacking multiple unpaid orders that hold
    # stock. A pending or payment_failed order with an unexpired
    # payment window must be resolved first.
    active_order = Order.query.filter(
        Order.user_id == user_id,
        Order.status.in_(["pending", "payment_failed"]),
        Order.payment_expires_at > datetime.utcnow()
    ).first()

    if active_order:
        return error(
            f"You already have an unpaid order ({active_order.order_number}) "
            f"awaiting payment. Complete or cancel it before placing a new order."
        )

    try:
        # ── Get cart ──────────────────────────────────────────
        cart = Cart.query.filter_by(user_id=user_id).first()

        if not cart or cart.is_empty():
            return error("Your cart is empty")

        cart_items = CartItem.query.filter_by(cart_id=cart.id).all()

        if not cart_items:
            return error("Your cart is empty")

        # ── Resolve shipping address ──────────────────────────
        # Handles: saved address / inline address (with dedup + optional
        # save) / default address fallback.  See _resolve_shipping_address.
        shipping, addr_error = _resolve_shipping_address(user_id, data)
        if addr_error:
            return addr_error

        # ── Lock variants + validate stock + calculate totals ───
        # with_for_update() issues SELECT ... FOR UPDATE so concurrent
        # requests targeting the same row must wait.  Stock is re-checked
        # against the locked row, guaranteeing that only one request can
        # reduce a given variant's stock at a time.
        locked_variants = {}   # variant_id → locked ProductVariant instance
        stock_errors    = []
        subtotal        = 0.0

        for item in cart_items:
            variant = (
                db.session.query(ProductVariant)
                .filter(ProductVariant.id == item.variant_id)
                .with_for_update()
                .first()
            )

            if not variant or not variant.is_active:
                label = getattr(variant, "label", None) or f"item #{item.variant_id}"
                stock_errors.append(f"'{label}' is no longer available")
                continue

            if item.quantity > variant.stock_qty:
                product_name = (
                    variant.product.name if variant.product else "product"
                )
                stock_errors.append(
                    f"Only {variant.stock_qty} units available "
                    f"for '{product_name} — {variant.label}'"
                )
                continue

            locked_variants[item.variant_id] = variant
            subtotal += float(variant.effective_price()) * item.quantity

        if stock_errors:
            return error(" | ".join(stock_errors))

        subtotal        = round(subtotal, 2)
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
            # Payment must be completed within 15 minutes (UTC)
            payment_expires_at  = datetime.utcnow() + timedelta(minutes=15),
        )
        db.session.add(order)
        db.session.flush()   # gets order.id before final commit

        # ── Create order items + reduce stock ─────────────────
        # Reuse the locked variant instances acquired above — no extra
        # queries, and the lock is still held within this transaction.
        for item in cart_items:
            variant    = locked_variants[item.variant_id]
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

    # ── Pre-flight expiry ─────────────────────────────────────
    # Expire ALL stale pending/payment_failed orders for this user
    # BEFORE running the main query.  Without this, the SQL filter
    # applied when status="pending" excludes orders whose window has
    # elapsed, so the lazy pass below never sees them and they stay
    # "pending" in the DB until the background scheduler fires.
    try:
        stale = Order.query.filter(
            Order.user_id == user_id,
            Order.status.in_(["pending", "payment_failed"]),
            Order.payment_expires_at <= datetime.utcnow()
        ).all()
        if stale:
            if any(o.expire_if_needed() for o in stale):
                db.session.commit()
    except Exception:
        db.session.rollback()

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

    # ── Lazy expiry pass ──────────────────────────────────────
    # Expire any orders whose payment window has elapsed since the
    # scheduler last ran.  This guarantees the user always sees an
    # up-to-date status the moment they open "My Orders", even if
    # the background job hasn't fired yet.
    any_expired = False
    for order in orders:
        try:
            if order.expire_if_needed():
                any_expired = True
        except Exception:
            pass  # never let expiry logic crash the list response

    if any_expired:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

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
            # is_payment_expired is True for pending AND payment_failed
            # orders whose window has elapsed (lazy expiry above already
            # committed the DB change, so status will read "expired" for
            # those; this flag is a belt-and-suspenders guard for the
            # serialised snapshot).
            is_expired = order.status in ("pending", "payment_failed") and \
                         bool(expires_at and datetime.utcnow() > expires_at)

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
                # Use the model method so the list stays in sync with
                # any future changes to cancellability rules.
                "is_cancellable":     order.is_cancellable(),
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

    CANCELLABLE = ['pending', 'confirmed', 'processing']
    if order.status not in CANCELLABLE:
        return error(
            f"Order cannot be cancelled. Current status: {order.status}"
        )

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