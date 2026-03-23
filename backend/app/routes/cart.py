from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import secrets

from ..extensions import db
from ..models import Cart, CartItem, ProductVariant, Product
from ..utils.responses import error, success

# ── Blueprint ─────────────────────────────────────────────────
cart_bp = Blueprint("cart", __name__, url_prefix="/api/cart")


# ── Internal: Get or Create Cart ──────────────────────────────
def _get_or_create_cart(user_id=None, session_token=None):
    """
    Finds existing cart or creates a new one.

    Logged-in user  → find by user_id
    Guest user      → find by session_token
    No cart exists  → create new one

    Returns (cart, session_token)
    """
    if user_id:
        cart = Cart.query.filter_by(user_id=user_id).first()
        
        if not cart:
            cart = Cart(user_id=user_id)
            db.session.add(cart)
            db.session.commit()
        return cart, None

    # Guest cart
    if session_token:
        cart = Cart.query.filter_by(session_token=session_token).first()
        if cart:
            return cart, session_token

    # Create new guest cart with fresh token
    new_token = secrets.token_urlsafe(32)
    cart      = Cart(session_token=new_token)
    db.session.add(cart)
    db.session.commit()
    return cart, new_token


# ── Internal: Build Cart Response ─────────────────────────────
def _cart_response(cart):
    """
    Builds full cart data for API response.
    Includes all items with variant and product details.
    """
    items = (
        CartItem.query
        .filter_by(cart_id=cart.id)
        .all()
    )

    items_data = []
    for item in items:
        variant = item.variant
        product = variant.product if variant else None

        if not variant or not product:
            continue

        primary_img = product.primary_image()

        items_data.append({
            "cart_item_id":  item.id,
            "variant_id":    item.variant_id,
            "quantity":      item.quantity,
            "product_name":  product.name,
            "product_name_ta": product.name_ta,
            "variant_label": variant.label,
            "unit_price":    float(variant.effective_price()),
            "is_on_sale":    variant.is_on_sale(),
            "regular_price": float(variant.price),
            "line_total":    item.line_total(),
            "stock_qty":     variant.stock_qty,
            "is_in_stock":   variant.is_in_stock(),
            "image_url":     primary_img.image_url if primary_img else None,
            "slug":          product.slug,
            "added_at":      item.added_at.isoformat(),
        })

    return {
        "cart_id":      cart.id,
        "total_items":  sum(i["quantity"] for i in items_data),
        "subtotal":     round(sum(i["line_total"] for i in items_data), 2),
        "items":        items_data,
    }


# ── GET /api/cart ─────────────────────────────────────────────
@cart_bp.route("/", methods=["GET"])
def get_cart():
    """
    Returns current cart contents.

    Logged-in  → Authorization: Bearer <token>
    Guest      → X-Session-Token: <session_token> header

    Returns:
        200 → cart with all items
    """
    # Try logged-in user first
    user_id       = None
    session_token = request.headers.get("X-Session-Token")

    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass

    # Look up existing cart — never create on GET
    cart = None
    if user_id:
        cart = Cart.query.filter_by(user_id=int(user_id)).first()
    elif session_token:
        cart = Cart.query.filter_by(session_token=session_token).first()

    if not cart:
        return success(
            message = "Cart fetched",
            data    = {"cart_id": None, "total_items": 0, "subtotal": 0.0, "items": []},
        )

    return success(message="Cart fetched", data=_cart_response(cart))


# ── POST /api/cart/add ────────────────────────────────────────
@cart_bp.route("/add", methods=["POST"])
def add_to_cart():
    """
    Adds a variant to cart or increases quantity if already exists.

    Request body (JSON):
        variant_id : int, required
        quantity   : int, optional (default 1)

    Headers:
        Authorization: Bearer <token>    (logged-in)
        X-Session-Token: <token>         (guest)

    Returns:
        200 → updated cart
        400 → validation error
        404 → variant not found
    """
    data       = request.get_json()
    variant_id = data.get("variant_id") if data else None
    quantity   = data.get("quantity", 1)

    # ── Validate ──────────────────────────────────────────────
    if not variant_id:
        return error("variant_id is required")
    if not isinstance(quantity, int) or quantity < 1:
        return error("Quantity must be a positive integer")

    # ── Check variant exists and is active ────────────────────
    variant = ProductVariant.query.filter_by(
        id        = variant_id,
        is_active = True
    ).first()

    if not variant:
        return error("Product variant not found", 404)

    # ── Check stock ───────────────────────────────────────────
    if not variant.is_in_stock():
        return error("This product is currently out of stock")

    if quantity > variant.stock_qty:
        return error(
            f"Only {variant.stock_qty} units available for '{variant.label}'"
        )

    # ── Get cart ──────────────────────────────────────────────
    user_id       = None
    session_token = request.headers.get("X-Session-Token")

    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass

    cart, new_token = _get_or_create_cart(
        user_id       = int(user_id) if user_id else None,
        session_token = session_token
    )

    # ── Add or update item ────────────────────────────────────
    existing = CartItem.query.filter_by(
        cart_id    = cart.id,
        variant_id = variant_id
    ).first()

    if existing:
        # Already in cart — increase quantity
        new_qty = existing.quantity + quantity
        if new_qty > variant.stock_qty:
            return error(
                f"Cannot add {quantity} more. "
                f"Only {variant.stock_qty - existing.quantity} units remaining."
            )
        existing.quantity = new_qty
    else:
        # New item
        cart_item = CartItem(
            cart_id    = cart.id,
            variant_id = variant_id,
            quantity   = quantity
        )
        db.session.add(cart_item)

    db.session.commit()

    response_data = _cart_response(cart)
    if new_token:
        response_data["session_token"] = new_token

    return success(message="Item added to cart", data=response_data)


# ── PATCH /api/cart/update/<cart_item_id> ─────────────────────
@cart_bp.route("/update/<int:cart_item_id>", methods=["PATCH"])
def update_cart_item(cart_item_id):
    """
    Updates quantity of a specific cart item.
    If quantity is 0 → removes the item.

    URL param:
        cart_item_id → CartItem id

    Request body (JSON):
        quantity : int, required (0 = remove)

    Returns:
        200 → updated cart
        400 → invalid quantity
        404 → cart item not found
    """
    data     = request.get_json()
    quantity = data.get("quantity") if data else None

    if quantity is None:
        return error("Quantity is required")
    if not isinstance(quantity, int) or quantity < 0:
        return error("Quantity must be 0 or a positive integer")

    # ── Find cart item ────────────────────────────────────────
    item = CartItem.query.get(cart_item_id)
    if not item:
        return error("Cart item not found", 404)

    # ── Remove if quantity is 0 ───────────────────────────────
    if quantity == 0:
        cart = item.cart
        db.session.delete(item)
        db.session.commit()
        return success(
            message = "Item removed from cart",
            data    = _cart_response(cart)
        )

    # ── Check stock ───────────────────────────────────────────
    variant = item.variant
    if quantity > variant.stock_qty:
        return error(
            f"Only {variant.stock_qty} units available for '{variant.label}'"
        )

    item.quantity = quantity
    db.session.commit()

    return success(
        message = "Cart updated",
        data    = _cart_response(item.cart)
    )


# ── DELETE /api/cart/remove/<cart_item_id> ────────────────────
@cart_bp.route("/remove/<int:cart_item_id>", methods=["DELETE"])
def remove_from_cart(cart_item_id):
    """
    Removes a specific item from cart completely.

    URL param:
        cart_item_id → CartItem id

    Returns:
        200 → updated cart
        404 → cart item not found
    """
    item = CartItem.query.get(cart_item_id)
    if not item:
        return error("Cart item not found", 404)

    cart = item.cart
    db.session.delete(item)
    db.session.commit()

    return success(
        message = "Item removed from cart",
        data    = _cart_response(cart)
    )


# ── DELETE /api/cart/clear ────────────────────────────────────
@cart_bp.route("/clear", methods=["DELETE"])
def clear_cart():
    """
    Removes all items from cart.
    Cart itself is kept — just emptied.

    Headers:
        Authorization: Bearer <token>    (logged-in)
        X-Session-Token: <token>         (guest)

    Returns:
        200 → empty cart
    """
    user_id       = None
    session_token = request.headers.get("X-Session-Token")

    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass

    cart, _ = _get_or_create_cart(
        user_id       = int(user_id) if user_id else None,
        session_token = session_token
    )

    cart.clear()

    return success(
        message = "Cart cleared",
        data    = _cart_response(cart)
    )


# ── POST /api/cart/merge ──────────────────────────────────────
@cart_bp.route("/merge", methods=["POST"])
@jwt_required()
def merge_cart():
    """
    Merges guest cart into logged-in user's cart.
    Called immediately after login if guest had items in cart.

    Request body (JSON):
        session_token : string, required

    Header:
        Authorization: Bearer <access_token>

    Returns:
        200 → merged cart
        400 → missing session token
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()
    token   = data.get("session_token") if data else None

    if not token:
        return error("session_token is required")

    # ── Find guest cart ───────────────────────────────────────
    guest_cart = Cart.query.filter_by(session_token=token).first()
    if not guest_cart or guest_cart.is_empty():
        return success(
            message = "Nothing to merge",
            data    = _cart_response(
                Cart.query.filter_by(user_id=user_id).first()
                or Cart(user_id=user_id)
            )
        )

    # ── Get or create user cart ───────────────────────────────
    user_cart = Cart.query.filter_by(user_id=user_id).first()
    if not user_cart:
        user_cart = Cart(user_id=user_id)
        db.session.add(user_cart)
        db.session.flush()

    # ── Merge items ───────────────────────────────────────────
    # Snapshot with .all() before any mutations.
    # Do NOT reassign guest_item.cart_id — with cascade="all, delete-orphan"
    # and lazy="dynamic", SQLAlchemy's cascade can delete reassigned items
    # when the guest cart is later deleted. Instead, create new CartItem rows
    # for the user cart and let the guest cart's items be cascade-deleted.
    guest_items = guest_cart.items.all()

    for guest_item in guest_items:
        existing = CartItem.query.filter_by(
            cart_id    = user_cart.id,
            variant_id = guest_item.variant_id
        ).first()

        if existing:
            # Combine quantities — cap at stock limit
            variant  = guest_item.variant
            combined = existing.quantity + guest_item.quantity
            existing.quantity = min(combined, variant.stock_qty)
        else:
            # Create a new item in the user cart
            db.session.add(CartItem(
                cart_id    = user_cart.id,
                variant_id = guest_item.variant_id,
                quantity   = guest_item.quantity,
            ))

    # ── Delete guest cart (cascades to its original items) ────
    db.session.delete(guest_cart)
    db.session.commit()

    return success(
        message = "Cart merged successfully",
        data    = _cart_response(user_cart)
    )