import os
import re
import uuid
import time
import shutil
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import (
    User, Product, ProductVariant, ProductImage,
    Category, Order, OrderItem, Payment,
    Review, Banner, ShippingRule, CartItem
)
from werkzeug.utils import secure_filename
from flask import request, jsonify, current_app

# ── Blueprint ─────────────────────────────────────────────────
admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ── Helpers ───────────────────────────────────────────────────
def error(message, code=400):
    return jsonify({"success": False, "message": message}), code

def success(message, data=None, code=200):
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code


# ── Admin Guard ───────────────────────────────────────────────
def admin_required(fn):
    """
    Decorator that checks user is logged in AND is admin.
    Use on every admin route instead of just @jwt_required().

    Usage:
        @admin_bp.route("/something")
        @admin_required
        def something():
            ...
    """
    from functools import wraps

    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        user    = User.query.get(user_id)

        if not user or not user.is_admin():
            return error("Admin access required", 403)

        return fn(*args, **kwargs)
    return wrapper


# ════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════

# ── GET /api/admin/dashboard ──────────────────────────────────
@admin_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    """
    Returns key metrics for admin dashboard homepage.
    Accepts optional date_from / date_to query params (YYYY-MM-DD).
    Defaults to first day of current month → today.

    Returns:
        200 → sales, orders, users, revenue stats
    """
    now           = datetime.utcnow()
    date_from_str = request.args.get("date_from")
    date_to_str   = request.args.get("date_to")

    if date_from_str:
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d")
    else:
        date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if date_to_str:
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, microsecond=999999
        )
    else:
        date_to = now

    REVENUE_STATUSES = ["confirmed", "processing", "shipped", "delivered"]

    # ── Order counts (in date range) ──────────────────────────
    total_orders = Order.query.filter(
        Order.created_at >= date_from,
        Order.created_at <= date_to
    ).count()

    # ── Revenue (in date range, valid statuses only) ───────────
    revenue_total = db.session.query(
        func.sum(Order.total)
    ).filter(
        Order.created_at >= date_from,
        Order.created_at <= date_to,
        Order.status.in_(REVENUE_STATUSES)
    ).scalar() or 0

    # ── Users registered in date range ────────────────────────
    total_users = User.query.filter(
        User.role        == "customer",
        User.created_at  >= date_from,
        User.created_at  <= date_to
    ).count()

    # ── Orders by status (in date range) ──────────────────────
    status_counts = {}
    for status in ["cancelled", "confirmed", "delivered", "expired",
                   "pending", "processing", "refunded", "shipped"]:
        status_counts[status] = Order.query.filter(
            Order.status     == status,
            Order.created_at >= date_from,
            Order.created_at <= date_to
        ).count()

    # ── Top 5 selling products (in date range) ────────────────
    top_products = (
        db.session.query(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("total_sold"),
            func.sum(OrderItem.line_total).label("total_revenue")
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to,
            Order.status.in_(REVENUE_STATUSES)
        )
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
        .all()
    )

    # ── Pending reviews (submitted in date range) ─────────────
    pending_reviews = Review.query.filter(
        Review.is_approved == False,
        Review.created_at  >= date_from,
        Review.created_at  <= date_to
    ).count()

    # ── Recent orders (in date range, last 8) ─────────────────
    recent_orders = (
        Order.query
        .filter(
            Order.created_at >= date_from,
            Order.created_at <= date_to
        )
        .order_by(Order.created_at.desc())
        .limit(8)
        .all()
    )

    return success(
        message = "Dashboard fetched",
        data    = {
            "date_from": date_from.strftime("%Y-%m-%d"),
            "date_to":   date_to.strftime("%Y-%m-%d"),
            "orders": {
                "total":     total_orders,
                "by_status": status_counts,
            },
            "revenue": {
                "total": float(revenue_total),
            },
            "users": {
                "total": total_users,
            },
            "top_products": [
                {
                    "name":          p.product_name,
                    "total_sold":    int(p.total_sold),
                    "total_revenue": float(p.total_revenue),
                }
                for p in top_products
            ],
            "pending_reviews": pending_reviews,
            "recent_orders": [
                {
                    "order_number":  o.order_number,
                    "customer_name": o.shipping_name,
                    "created_at":    o.created_at.isoformat() if o.created_at else None,
                    "total":         float(o.total),
                    "status":        o.status,
                }
                for o in recent_orders
            ],
        }
    )


# ════════════════════════════════════════════════════════════
# ORDERS
# ════════════════════════════════════════════════════════════

# ── GET /api/admin/orders ─────────────────────────────────────
@admin_bp.route("/orders", methods=["GET"])
@admin_required
def list_orders():
    """
    Returns paginated list of all orders.

    Query params:
        page     → page number (default 1)
        per_page → orders per page (default 20)
        status   → filter by status
        search   → search by order number or customer name
    """
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status   = request.args.get("status",   None)
    search   = request.args.get("search",   "").strip()

    query = (
        db.session.query(Order, User)
        .outerjoin(User, User.id == Order.user_id)
    )

    if status:
        query = query.filter(Order.status == status)

    if search:
        query = query.filter(
            db.or_(
                Order.order_number.ilike(f"%{search}%"),
                Order.shipping_name.ilike(f"%{search}%"),
                Order.shipping_phone.ilike(f"%{search}%")
            )
        )

    paginated = (
        query
        .order_by(Order.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    orders = []
    for order, user in paginated.items:
        d = order.to_dict(include_items=True)
        d["customer"] = user.name if user else "Guest"
        orders.append(d)

    return success(
        message = "Orders fetched",
        data    = {
            "orders": orders,
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


# ── GET /api/admin/orders/<order_number> ──────────────────────
@admin_bp.route("/orders/<order_number>", methods=["GET"])
@admin_required
def get_order(order_number):
    """
    Returns full detail for a single order.

    Returns:
        200 → order with items and shipping address
        404 → order not found
    """
    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return error("Order not found", 404)

    return success(
        message = "Order fetched",
        data    = {"order": order.to_dict(include_items=True)}
    )


# ── PATCH /api/admin/orders/<order_number>/status ─────────────
@admin_bp.route("/orders/<order_number>/status", methods=["PATCH"])
@admin_required
def update_order_status(order_number):
    """
    Updates order status.
    Admin manually moves orders through the pipeline.

    Request body (JSON):
        status : string, required

    Returns:
        200 → updated order
        400 → invalid status
        404 → order not found
    """
    data   = request.get_json()
    status = data.get("status") if data else None

    all_statuses = [
        "pending", "payment_failed", "confirmed", "processing",
        "shipped", "delivered", "cancelled", "expired", "refunded"
    ]

    if not status or status not in all_statuses:
        return error(f"Invalid status: '{status}'")

    order = Order.query.filter_by(order_number=order_number).first()
    if not order:
        return error("Order not found", 404)

    # ── Transition rules ──────────────────────────────────────
    LOCKED = {"pending", "payment_failed", "cancelled", "refunded", "expired"}
    TRANSITIONS = {
        "confirmed":  "processing",
        "processing": "shipped",
        "shipped":    "delivered",
    }

    if order.status in LOCKED:
        return error(f"Order status '{order.status}' cannot be changed")

    allowed_next = TRANSITIONS.get(order.status)
    if not allowed_next:
        return error(f"Order status '{order.status}' cannot be changed")

    if status != allowed_next:
        return error(
            f"Invalid transition: {order.status} → {status}. "
            f"Only confirmed→processing→shipped→delivered allowed"
        )

    order.status = status
    db.session.commit()

    return success(
        message = f"Order status updated to '{status}'",
        data    = {"order": order.to_dict(include_items=True)}
    )


# ════════════════════════════════════════════════════════════
# PRODUCTS
# ════════════════════════════════════════════════════════════

# ── GET /api/admin/products ───────────────────────────────────
@admin_bp.route("/products", methods=["GET"])
@admin_required
def list_products():
    """
    Returns all products including inactive ones.
    Admin sees everything — customers only see active.
    """
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search   = request.args.get("search",   "").strip()

    query = Product.query

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f"%{search}%"),
                Product.name_ta.ilike(f"%{search}%"),
                Product.slug.ilike(f"%{search}%")
            )
        )

    paginated = (
        query
        .order_by(Product.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    def _product_dict(p):
        d = p.to_dict(include_variants=True, include_images=True)
        d["category"] = {"name": p.category.name} if p.category else None
        return d

    return success(
        message = "Products fetched",
        data    = {
            "products": [_product_dict(p) for p in paginated.items],
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


# ── POST /api/admin/products ──────────────────────────────────
@admin_bp.route("/products", methods=["POST"])
@admin_required
def create_product():
    """
    Creates a new product with at least one variant.

    Request body (JSON):
        name        : string, required
        name_ta     : string, optional
        category_id : int,    required
        description : string, optional
        short_desc  : string, optional
        source_info : string, optional
        is_featured : bool,   optional
        variants    : list,   required (at least one)
            - label       : string, required
            - price       : float,  required
            - sale_price  : float,  optional
            - stock_qty   : int,    required
            - weight_grams: int,    optional
            - sku         : string, optional

    Returns:
        201 → created product
        400 → validation error
    """
    import json
    from slugify import slugify

    # Handle both JSON and multipart/form-data
    if request.content_type and 'multipart/form-data' in request.content_type:
        data  = request.form
        files = request.files.getlist('images')
    else:
        data  = request.get_json(silent=True) or {}
        files = []

    name        = (data.get("name",        "") or "").strip()
    name_ta     = (data.get("name_ta",     "") or "").strip() or None
    category_id = data.get("category_id")
    description = (data.get("description", "") or "").strip() or None
    short_desc  = (data.get("short_desc",  "") or "").strip() or None
    source_info = (data.get("source_info", "") or "").strip() or None
    is_featured = data.get("is_featured", False)
    if isinstance(is_featured, str):
        is_featured = is_featured.lower() in ('true', '1', 'yes')

    # Variants — list in JSON mode, JSON string in multipart mode
    variants_raw = data.get("variants", "[]")
    variants = json.loads(variants_raw) if isinstance(variants_raw, str) else variants_raw

    # ── Validate ──────────────────────────────────────────────
    if not name:
        return error("Product name is required")
    if not category_id:
        return error("category_id is required")
    if not variants or len(variants) == 0:
        return error("At least one variant is required")

    # ── Generate unique slug ──────────────────────────────────
    base_slug = slugify(name)
    slug      = base_slug
    counter   = 1
    while Product.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    # ── Validate variants ─────────────────────────────────────
    for i, v in enumerate(variants):
        if not v.get("label", "").strip():
            return error(f"Variant {i+1}: label is required")
        if not v.get("price"):
            return error(f"Variant {i+1}: price is required")
        if v.get("stock_qty") is None:
            return error(f"Variant {i+1}: stock_qty is required")

    # ── Create product ────────────────────────────────────────
    try:
        base_price = min(float(v["price"]) for v in variants)

        product = Product(
            name        = name,
            name_ta     = name_ta,
            category_id = category_id,
            slug        = slug,
            description = description,
            short_desc  = short_desc,
            source_info = source_info,
            base_price  = base_price,
            is_featured = is_featured,
            is_active   = True
        )
        db.session.add(product)
        db.session.flush()

        # ── Create variants ───────────────────────────────────
        for v in variants:
            new_price      = float(v["price"])
            new_sale_price = float(v["sale_price"]) if v.get("sale_price") else None
            # Set old_price to the regular price when a sale is active
            new_old_price  = new_price if new_sale_price is not None else None
            variant = ProductVariant(
                product_id   = product.id,
                label        = v["label"].strip(),
                sku          = v.get("sku",          "").strip() or None,
                price        = new_price,
                sale_price   = new_sale_price,
                old_price    = new_old_price,
                stock_qty    = int(v["stock_qty"]),
                weight_grams = int(v["weight_grams"]) if v.get("weight_grams") else None,
                is_active    = True
            )
            db.session.add(variant)

        db.session.commit()

        # ── Save directly uploaded images ─────────────────────
        for idx, file in enumerate(files):
            if file and allowed_file(file.filename):
                ext      = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{product.slug}-{uuid.uuid4().hex[:8]}.{ext}"
                upload_folder = os.path.abspath(os.path.join(
                    current_app.root_path, '..', '..', 'frontend',
                    'static', 'images', 'products'
                ))
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, filename))
                db.session.add(ProductImage(
                    product_id = product.id,
                    image_url  = f"/static/images/products/{filename}",
                    alt_text   = product.name,
                    sort_order = idx,
                    is_primary = (idx == 0),
                ))
        if files:
            db.session.commit()

        return success(
            message = "Product created successfully",
            data    = {
                "product": product.to_dict(
                    include_variants=True,
                    include_images=True
                )
            },
            code = 201
        )

    except Exception as e:
        db.session.rollback()
        return error(str(e), 500)


# ── GET /api/admin/products/<product_id> ──────────────────────
@admin_bp.route("/products/<int:product_id>", methods=["GET"])
@admin_required
def get_product(product_id):
    """
    Returns full detail for a single product including variants and images.

    Returns:
        200 → product
        404 → product not found
    """
    try:
        product = Product.query.get(product_id)
        if not product:
            return error("Product not found", 404)

        return success(
            message = "Product fetched",
            data    = {
                "product": product.to_dict(
                    include_variants=True,
                    include_images=True
                )
            }
        )
    except Exception as e:
        return error(str(e), 500)


# ── PATCH /api/admin/products/<product_id> ────────────────────
@admin_bp.route("/products/<int:product_id>", methods=["PATCH"])
@admin_required
def update_product(product_id):
    """
    Updates product fields.
    Only provided fields are updated — others unchanged.

    Returns:
        200 → updated product
        404 → product not found
    """
    import json

    product = Product.query.get(product_id)
    if not product:
        return error("Product not found", 404)

    # Handle both multipart/form-data and JSON
    if request.content_type and 'multipart/form-data' in request.content_type:
        data  = request.form
        files = request.files.getlist('images')
    else:
        data  = request.get_json() or {}
        files = []

    if not data and not files:
        return error("Request body is required")

    # Update only provided fields
    if "name"        in data: product.name        = (data.get("name")        or "").strip()
    if "name_ta"     in data: product.name_ta     = (data.get("name_ta")     or "").strip() or None
    if "category_id" in data: product.category_id = data["category_id"]
    if "description" in data: product.description = (data.get("description") or "").strip() or None
    if "short_desc"  in data: product.short_desc  = (data.get("short_desc")  or "").strip() or None
    if "source_info" in data: product.source_info = (data.get("source_info") or "").strip() or None
    if "is_active"   in data:
        val = data["is_active"]
        product.is_active = (val.lower() in ('true', '1', 'yes')) if isinstance(val, str) else bool(val)
    if "is_featured" in data:
        val = data["is_featured"]
        product.is_featured = (val.lower() in ('true', '1', 'yes')) if isinstance(val, str) else bool(val)

    # ── Upsert variants if provided ───────────────────────────
    if "variants" in data:
        variants_raw = data.get("variants", "[]")
        variants = json.loads(variants_raw) if isinstance(variants_raw, str) else variants_raw

        if variants:
            try:
                # Index existing variants by ID — never delete+recreate,
                # always update in place to preserve FK references in
                # cart_items and order_items.
                existing_variants = {
                    v.id: v for v in product.variants.all()
                }
                submitted_ids = set()

                for v_data in variants:
                    if not (v_data.get("label") or "").strip() or not v_data.get("price"):
                        continue

                    v_id = v_data.get("id")
                    if v_id and int(v_id) in existing_variants:
                        # UPDATE existing variant in place — preserves its ID
                        variant = existing_variants[int(v_id)]
                        submitted_ids.add(int(v_id))
                    else:
                        # NEW variant — no existing ID to preserve
                        variant = ProductVariant(product_id=product.id)
                        db.session.add(variant)

                    # Safely parse sale_price — treat '' and None both as NULL
                    raw = v_data.get("sale_price")
                    if raw == "" or raw is None:
                        new_sale_price = None
                    else:
                        try:
                            new_sale_price = float(raw)
                        except (TypeError, ValueError):
                            new_sale_price = None

                    # Auto-shift old_price before overwriting sale_price.
                    # Only meaningful for existing variants (new ones have no history).
                    try:
                        if variant.id:
                            effective_current = (
                                float(variant.sale_price) if variant.sale_price is not None
                                else float(variant.price) if variant.price is not None
                                else None
                            )
                            if effective_current is not None:
                                compare_new = (
                                    new_sale_price if new_sale_price is not None
                                    else float(v_data.get("price") or 0)
                                )
                                if compare_new != effective_current:
                                    variant.old_price = effective_current
                    except (TypeError, ValueError):
                        pass  # never crash product save over price history

                    # Update fields in place
                    variant.label      = (v_data.get("label") or "").strip()
                    variant.price      = float(v_data.get("price") or 0)
                    variant.sale_price = new_sale_price
                    variant.stock_qty  = int(v_data.get("stock_qty") or 0)
                    variant.sku        = (v_data.get("sku") or "").strip() or None
                    variant.weight_grams = int(v_data["weight_grams"]) if v_data.get("weight_grams") else None
                    variant.is_active  = bool(v_data.get("is_active", True))

                # Remove variants not in this submission —
                # but NEVER delete one referenced by a cart_item; deactivate instead.
                for v_id, variant in existing_variants.items():
                    if v_id not in submitted_ids:
                        if CartItem.query.filter_by(variant_id=v_id).first():
                            variant.is_active = False
                        else:
                            db.session.delete(variant)

                db.session.flush()

            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Variant update error: {e}")
                return error(str(e), 500)

    # Clean up deactivated variants with no cart or order references
    # (leftovers from previous broken delete+recreate saves)
    for v in ProductVariant.query.filter_by(product_id=product_id, is_active=False).all():
        if (not CartItem.query.filter_by(variant_id=v.id).first() and
                not OrderItem.query.filter_by(variant_id=v.id).first()):
            db.session.delete(v)

    # Recalculate base_price from active variants
    active_variants = product.variants.filter_by(is_active=True).all()
    if active_variants:
        product.base_price = min(float(v.effective_price()) for v in active_variants)

    db.session.commit()

    # ── Save newly uploaded images ─────────────────────────
    if files:
        has_primary = ProductImage.query.filter_by(
            product_id=product_id, is_primary=True
        ).first() is not None
        existing_count = ProductImage.query.filter_by(product_id=product_id).count()

        for idx, file in enumerate(files):
            if file and allowed_file(file.filename):
                ext      = file.filename.rsplit('.', 1)[1].lower()
                filename = f"{product.slug}-{uuid.uuid4().hex[:8]}.{ext}"
                save_folder = os.path.abspath(os.path.join(
                    current_app.root_path, '..', '..', 'frontend',
                    'static', 'images', 'products'
                ))
                os.makedirs(save_folder, exist_ok=True)
                file.save(os.path.join(save_folder, filename))
                db.session.add(ProductImage(
                    product_id = product_id,
                    image_url  = f"/static/images/products/{filename}",
                    alt_text   = product.name,
                    sort_order = existing_count + idx,
                    is_primary = (not has_primary and idx == 0),
                ))
        db.session.commit()

    return success(
        message = "Product updated",
        data    = {
            "product": product.to_dict(
                include_variants=True,
                include_images=True
            )
        }
    )


# ── DELETE /api/admin/products/<product_id> ───────────────────
@admin_bp.route("/products/<int:product_id>", methods=["DELETE"])
@admin_required
def delete_product(product_id):
    """
    Soft deletes a product by setting is_active=False.
    Never hard deletes — order history must stay intact.

    Returns:
        200 → product deactivated
        404 → product not found
    """
    product = Product.query.get(product_id)
    if not product:
        return error("Product not found", 404)

    product.is_active = False

    db.session.commit()

    return success(message=f"Product '{product.name}' deactivated successfully")


# ── PATCH /api/admin/products/<product_id>/toggle-featured ───
@admin_bp.route("/products/<int:product_id>/toggle-featured", methods=["PATCH"])
@admin_required
def toggle_featured(product_id):
    product = Product.query.get(product_id)
    if not product:
        return error("Product not found", 404)
    product.is_featured = not product.is_featured
    db.session.commit()
    return success(
        message = f"Product {'featured' if product.is_featured else 'unfeatured'}",
        data    = {"is_featured": product.is_featured}
    )


# ════════════════════════════════════════════════════════════
# REVIEWS
# ════════════════════════════════════════════════════════════

# ── GET /api/admin/reviews ────────────────────────────────────
@admin_bp.route("/reviews", methods=["GET"])
@admin_required
def list_reviews():
    """
    Returns reviews pending approval.

    Query params:
        status → 'pending', 'approved' (omit or any other value = all)
    """
    status = request.args.get("status", "").strip()

    query = Review.query
    if status == "pending":
        query = query.filter_by(is_approved=False)
    elif status == "approved":
        query = query.filter_by(is_approved=True)
    # empty / omitted → no filter → return all

    reviews = query.order_by(Review.created_at.desc()).all()

    product_cache = {}
    reviews_data  = []
    for r in reviews:
        if r.product_id not in product_cache:
            product_cache[r.product_id] = Product.query.get(r.product_id)
        product = product_cache[r.product_id]

        d = r.to_dict()
        d["product_name"] = product.name if product else "Unknown"
        reviews_data.append(d)

    return success(
        message = "Reviews fetched",
        data    = {
            "reviews": reviews_data,
            "total":   len(reviews_data)
        }
    )


# ── PATCH /api/admin/reviews/<review_id>/approve ─────────────
@admin_bp.route("/reviews/<int:review_id>/approve", methods=["PATCH"])
@admin_required
def approve_review(review_id):
    """
    Approves a review — makes it visible to customers.

    Returns:
        200 → review approved
        404 → review not found
    """
    review = Review.query.get(review_id)
    if not review:
        return error("Review not found", 404)

    review.approve()
    db.session.commit()

    return success(
        message = "Review approved",
        data    = {"review": review.to_dict()}
    )


# ── DELETE /api/admin/reviews/<review_id> ────────────────────
@admin_bp.route("/reviews/<int:review_id>", methods=["DELETE"])
@admin_required
def delete_review(review_id):
    """
    Deletes a review permanently.
    Used for spam or inappropriate content.

    Returns:
        200 → review deleted
        404 → review not found
    """
    review = Review.query.get(review_id)
    if not review:
        return error("Review not found", 404)

    db.session.delete(review)
    db.session.commit()

    return success(message="Review deleted")


# ════════════════════════════════════════════════════════════
# USERS
# ════════════════════════════════════════════════════════════

# ── GET /api/admin/users ──────────────────────────────────────
@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    """
    Returns paginated list of all customers.

    Query params:
        page     → page number (default 1)
        per_page → users per page (default 20)
        search   → search by name, email, phone
    """
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search   = request.args.get("search",   "").strip()

    query = User.query.filter_by(role="customer")

    if search:
        query = query.filter(
            db.or_(
                User.name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.phone.ilike(f"%{search}%")
            )
        )

    paginated = (
        query
        .order_by(User.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return success(
        message = "Users fetched",
        data    = {
            "users": [u.to_dict() for u in paginated.items],
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


# ── PATCH /api/admin/users/<user_id>/toggle ───────────────────
@admin_bp.route("/users/<int:user_id>/toggle", methods=["PATCH"])
@admin_required
def toggle_user(user_id):
    """
    Activates or deactivates a user account.
    Deactivated users cannot log in.

    Returns:
        200 → user status toggled
        400 → cannot deactivate yourself
        404 → user not found
    """
    admin_id = int(get_jwt_identity())

    if user_id == admin_id:
        return error("You cannot deactivate your own account")

    user = User.query.get(user_id)
    if not user:
        return error("User not found", 404)

    user.is_active = not user.is_active
    db.session.commit()

    status = "activated" if user.is_active else "deactivated"
    return success(
        message = f"User {status} successfully",
        data    = {"user": user.to_dict()}
    )


# ════════════════════════════════════════════════════════════
# BANNERS
# ════════════════════════════════════════════════════════════

def parse_date(val):
    """Parse a YYYY-MM-DD string to a date object; return None on any failure."""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except Exception:
        return None

# ── GET /api/admin/banners ────────────────────────────────────
@admin_bp.route("/banners", methods=["GET"])
@admin_required
def list_banners():
    """Returns all banners including inactive ones."""
    banners = Banner.query.order_by(Banner.sort_order.asc()).all()
    return success(
        message = "Banners fetched",
        data    = {"banners": [b.to_dict() for b in banners]}
    )


# ── POST /api/admin/banners ───────────────────────────────────
@admin_bp.route("/banners", methods=["POST"])
@admin_required
def create_banner():
    """
    Creates a new banner.

    Request body (JSON):
        title      : string, required
        image_url  : string, optional
        link_url   : string, optional
        sort_order : int,    optional
        is_active  : bool,   optional (default True)
        start_date : string, optional (YYYY-MM-DD)
        end_date   : string, optional (YYYY-MM-DD)
    """
    data  = request.get_json() or {}
    title = (data.get("title") or "").strip()

    if not title:
        return jsonify({"success": False, "message": "Title is required"}), 400

    try:
        banner = Banner(
            title      = title,
            image_url  = (data.get("image_url") or "").strip(),
            link_url   = (data.get("link_url")   or "").strip() or None,
            position   = "sidebar",
            sort_order = int(data.get("sort_order") or 0),
            is_active  = bool(data.get("is_active", True)),
            start_date = parse_date(data.get("start_date")),
            end_date   = parse_date(data.get("end_date")),
        )
        db.session.add(banner)
        db.session.commit()
        return jsonify({"success": True, "banner": banner.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500


# ── PATCH /api/admin/banners/<banner_id> ──────────────────────
@admin_bp.route("/banners/<int:banner_id>", methods=["PATCH"])
@admin_required
def update_banner(banner_id):
    """Updates a banner. Only provided fields are changed."""
    banner = Banner.query.get(banner_id)
    if not banner:
        return error("Banner not found", 404)

    data = request.get_json()
    if not data:
        return error("Request body is required")

    if "title"      in data: banner.title      = (data["title"]     or "").strip() or None
    if "image_url"  in data: banner.image_url  = (data["image_url"] or "").strip()
    if "link_url"   in data: banner.link_url   = (data["link_url"]  or "").strip() or None
    if "position"   in data: banner.position   = data["position"]
    if "sort_order" in data: banner.sort_order = int(data["sort_order"] or 0)
    if "is_active"  in data: banner.is_active  = bool(data["is_active"])
    if "start_date" in data: banner.start_date = parse_date(data["start_date"])
    if "end_date"   in data: banner.end_date   = parse_date(data["end_date"])

    db.session.commit()

    return success(
        message = "Banner updated",
        data    = {"banner": banner.to_dict()}
    )


# ── DELETE /api/admin/banners/<banner_id> ─────────────────────
@admin_bp.route("/banners/<int:banner_id>", methods=["DELETE"])
@admin_required
def delete_banner(banner_id):
    """Permanently deletes a banner."""
    banner = Banner.query.get(banner_id)
    if not banner:
        return error("Banner not found", 404)

    db.session.delete(banner)
    db.session.commit()

    return success(message="Banner deleted")


# ── POST /api/admin/banners/upload-image ──────────────────────
@admin_bp.route("/banners/upload-image", methods=["POST"])
@admin_required
def upload_banner_image():
    """
    Uploads a banner image and saves it to
    /static/images/products/banners/<filename>.

    Returns: { image_url: "/static/images/products/banners/<filename>" }
    """
    file = request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"error": "No file provided"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        return jsonify({"error": "Only JPG, PNG, WebP allowed"}), 400

    filename = f"banner_{int(time.time())}_{secure_filename(file.filename)}"

    save_dir = os.path.abspath(os.path.join(
        current_app.root_path, "..", "..",
        "frontend", "static", "images", "products", "banners"
    ))
    os.makedirs(save_dir, exist_ok=True)
    file.save(os.path.join(save_dir, filename))

    return jsonify({
        "image_url": f"/static/images/products/banners/{filename}"
    }), 200


# ════════════════════════════════════════════════════════════
# IMAGE MANAGER
# ════════════════════════════════════════════════════════════

def get_images_base():
    return os.path.abspath(os.path.join(
        current_app.root_path, "..", "..", "frontend", "static", "images"
    ))


def safe_path(base, *parts):
    """Return absolute path only if it stays inside base; else None."""
    full = os.path.abspath(os.path.join(base, *parts))
    if full != base and not full.startswith(base + os.sep):
        return None
    return full


# ── GET /api/admin/images/folders ─────────────────────────
@admin_bp.route("/images/folders", methods=["GET"])
@admin_required
def list_image_folders():
    """Returns a flat list of all sub-folder paths (relative to static/images/)."""
    base = get_images_base()
    folders = [""]  # root = ""
    for root, dirs, _ in os.walk(base):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for d in dirs:
            rel = os.path.relpath(os.path.join(root, d), base).replace(os.sep, "/")
            folders.append(rel)
    return jsonify({"folders": folders})


# ── GET /api/admin/images/list?folder=products/banners ────
@admin_bp.route("/images/list", methods=["GET"])
@admin_required
def list_images():
    """Returns all image files inside a folder (default: root)."""
    base   = get_images_base()
    folder = request.args.get("folder", "").strip("/")
    target = safe_path(base, folder) if folder else base
    if not target or not os.path.isdir(target):
        return error("Invalid folder", 400)

    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
    images = []
    for f in sorted(os.listdir(target)):
        if os.path.splitext(f)[1].lower() in exts and os.path.isfile(os.path.join(target, f)):
            rel = (folder + "/" + f) if folder else f
            images.append({
                "filename": f,
                "url":      f"/static/images/{rel}",
                "size":     os.path.getsize(os.path.join(target, f)),
            })
    return jsonify({"images": images})


# ── POST /api/admin/images/create-folder ──────────────────
@admin_bp.route("/images/create-folder", methods=["POST"])
@admin_required
def create_image_folder():
    base   = get_images_base()
    data   = request.get_json() or {}
    folder = (data.get("folder") or "").strip().strip("/")
    if not folder:
        return error("Folder name required")
    if not re.match(r'^[\w\-/]+$', folder):
        return error("Folder name may only contain letters, digits, hyphens, underscores, and slashes")
    target = safe_path(base, folder)
    if not target:
        return error("Invalid path", 400)
    os.makedirs(target, exist_ok=True)
    return jsonify({"success": True, "folder": folder})


# ── POST /api/admin/images/upload ─────────────────────────
@admin_bp.route("/images/upload", methods=["POST"])
@admin_required
def upload_image():
    base   = get_images_base()
    folder = request.form.get("folder", "").strip("/")
    file   = request.files.get("image")
    if not file or file.filename == "":
        return error("No file provided")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        return error("Unsupported file type")
    target_dir = safe_path(base, folder) if folder else base
    if not target_dir:
        return error("Invalid folder", 400)
    os.makedirs(target_dir, exist_ok=True)
    filename = f"{int(time.time())}_{secure_filename(file.filename)}"
    file.save(os.path.join(target_dir, filename))
    rel = (folder + "/" + filename) if folder else filename
    return jsonify({"success": True, "url": f"/static/images/{rel}", "filename": filename})


# ── DELETE /api/admin/images/delete-image ─────────────────
@admin_bp.route("/images/delete-image", methods=["DELETE"])
@admin_required
def delete_image():
    base     = get_images_base()
    data     = request.get_json() or {}
    folder   = (data.get("folder") or "").strip("/")
    filename = (data.get("filename") or "").strip()
    if not filename:
        return error("Filename required")
    target = safe_path(base, folder, filename) if folder else safe_path(base, filename)
    if not target or not os.path.isfile(target):
        return error("File not found", 404)
    os.remove(target)
    return jsonify({"success": True})


# ── DELETE /api/admin/images/delete-folder ────────────────
@admin_bp.route("/images/delete-folder", methods=["DELETE"])
@admin_required
def delete_image_folder():
    base   = get_images_base()
    data   = request.get_json() or {}
    folder = (data.get("folder") or "").strip().strip("/")
    if not folder:
        return error("Folder required")
    target = safe_path(base, folder)
    if not target or not os.path.isdir(target):
        return error("Folder not found", 404)
    shutil.rmtree(target)
    return jsonify({"success": True})


# ── PATCH /api/admin/images/rename-image ──────────────────
@admin_bp.route("/images/rename-image", methods=["PATCH"])
@admin_required
def rename_image():
    base     = get_images_base()
    data     = request.get_json() or {}
    folder   = (data.get("folder") or "").strip("/")
    old_name = (data.get("old_name") or "").strip()
    new_name = (data.get("new_name") or "").strip()
    if not old_name or not new_name:
        return error("old_name and new_name required")
    if not re.match(r'^[\w\-. ]+\.\w+$', new_name):
        return error("Invalid filename")
    old_path = safe_path(base, folder, old_name) if folder else safe_path(base, old_name)
    new_path = safe_path(base, folder, new_name) if folder else safe_path(base, new_name)
    if not old_path or not os.path.isfile(old_path):
        return error("File not found", 404)
    if not new_path:
        return error("Invalid new path", 400)
    os.rename(old_path, new_path)
    rel = (folder + "/" + new_name) if folder else new_name
    return jsonify({"success": True, "url": f"/static/images/{rel}"})


# ════════════════════════════════════════════════════════════
# SHIPPING RULES
# ════════════════════════════════════════════════════════════

# ── GET /api/admin/shipping-rules ─────────────────────────────
@admin_bp.route("/shipping-rules", methods=["GET"])
@admin_required
def list_shipping_rules():
    """Returns all shipping rules."""
    rules = ShippingRule.query.order_by(
        ShippingRule.min_order_value.asc()
    ).all()
    return success(
        message = "Shipping rules fetched",
        data    = {"rules": [r.to_dict() for r in rules]}
    )


# ── POST /api/admin/shipping-rules ────────────────────────────
@admin_bp.route("/shipping-rules", methods=["POST"])
@admin_required
def create_shipping_rule():
    """
    Creates a new shipping rule.

    Request body (JSON):
        name            : string, required
        min_order_value : float,  required
        charge          : float,  required (0 = free shipping)
    """
    data = request.get_json()

    name            = data.get("name",            "").strip() if data else ""
    min_order_value = data.get("min_order_value", None)
    charge          = data.get("charge",          None)

    if not name:
        return error("Rule name is required")
    if min_order_value is None:
        return error("min_order_value is required")
    if charge is None:
        return error("charge is required")

    rule = ShippingRule(
        name            = name,
        min_order_value = float(min_order_value),
        charge          = float(charge),
        is_active       = True
    )
    db.session.add(rule)
    db.session.commit()

    return success(
        message = "Shipping rule created",
        data    = {"rule": rule.to_dict()},
        code    = 201
    )


# ── PATCH /api/admin/shipping-rules/<rule_id> ─────────────────
@admin_bp.route("/shipping-rules/<int:rule_id>", methods=["PATCH"])
@admin_required
def update_shipping_rule(rule_id):
    """Updates a shipping rule."""
    rule = ShippingRule.query.get(rule_id)
    if not rule:
        return error("Shipping rule not found", 404)

    data = request.get_json()
    if not data:
        return error("Request body is required")

    if "name"            in data: rule.name            = data["name"].strip()
    if "min_order_value" in data: rule.min_order_value = float(data["min_order_value"])
    if "charge"          in data: rule.charge          = float(data["charge"])
    if "is_active"       in data: rule.is_active       = bool(data["is_active"])

    db.session.commit()

    return success(
        message = "Shipping rule updated",
        data    = {"rule": rule.to_dict()}
    )

# ── Allowed image extensions ───────────────────────────────
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Upload Product Image ───────────────────────────────────
@admin_bp.route('/products/<int:product_id>/images', methods=['POST'])
@jwt_required()
@admin_required
def upload_product_image(product_id):
    product = Product.query.get_or_404(product_id)

    if 'image' not in request.files:
        return jsonify({'message': 'No image file provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'message': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'message': 'Invalid file type. Use JPG, PNG or WEBP'}), 400

    # Generate unique filename
    ext      = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{product.slug}-{uuid.uuid4().hex[:8]}.{ext}"

    # Save path
    upload_folder = os.path.abspath(os.path.join(
        current_app.root_path, '..', '..', 'frontend', 'static', 'images', 'products'
    ))
    os.makedirs(upload_folder, exist_ok=True)
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)

    # Get sort order
    existing_count = ProductImage.query.filter_by(product_id=product_id).count()

    # First image for this product becomes primary
    has_primary = ProductImage.query.filter_by(
        product_id=product_id, is_primary=True
    ).first() is not None

    # Save to DB
    image = ProductImage(
        product_id = product_id,
        image_url  = f"/static/images/products/{filename}",
        alt_text   = product.name,
        sort_order = existing_count,
        is_primary = not has_primary,
    )
    db.session.add(image)
    db.session.commit()

    return jsonify({
        'message' : 'Image uploaded successfully',
        'image'   : {
            'id'        : image.id,
            'image_url' : image.image_url,
            'alt_text'  : image.alt_text,
            'sort_order': image.sort_order,
        }
    }), 201


# ── Delete Product Image ───────────────────────────────────
@admin_bp.route('/products/images/<int:image_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_product_image(image_id):
    image = ProductImage.query.get_or_404(image_id)

    # Delete file from disk
    try:
        filepath = os.path.abspath(os.path.join(
            current_app.root_path, '..', '..', 'frontend',
            image.image_url.lstrip('/')
        ))
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass  # non-critical

    db.session.delete(image)
    db.session.commit()

    return jsonify({'message': 'Image deleted'}), 200


# ── Get Product Images ─────────────────────────────────────
@admin_bp.route('/products/<int:product_id>/images', methods=['GET'])
@jwt_required()
@admin_required
def get_product_images(product_id):
    images = ProductImage.query.filter_by(
        product_id=product_id
    ).order_by(ProductImage.sort_order).all()

    return jsonify({
        'images': [{
            'id'        : img.id,
            'image_url' : img.image_url,
            'alt_text'  : img.alt_text,
            'sort_order': img.sort_order,
        } for img in images]
    }), 200


# ── Create Category on the fly ─────────────────────────────
@admin_bp.route('/categories', methods=['POST'])
@jwt_required()
@admin_required
def create_category():
    data = request.get_json()
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'message': 'Category name is required'}), 400

    # Auto-generate slug
    slug = name.lower().replace(' ', '-').replace('/', '-')

    # Check duplicate
    existing = Category.query.filter_by(slug=slug).first()
    if existing:
        return jsonify({
            'message'  : 'Category already exists',
            'category' : {
                'id'   : existing.id,
                'name' : existing.name,
                'slug' : existing.slug,
            }
        }), 200

    category = Category(
        name      = name,
        name_ta   = data.get('name_ta', '').strip() or None,
        slug      = slug,
        is_active = True,
    )
    db.session.add(category)
    db.session.commit()

    return jsonify({
        'message'  : 'Category created',
        'category' : {
            'id'   : category.id,
            'name' : category.name,
            'slug' : category.slug,
        }
    }), 201