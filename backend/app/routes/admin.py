import os
import uuid
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import (
    User, Product, ProductVariant, ProductImage,
    Category, Order, OrderItem, Payment,
    Review, Banner, ShippingRule
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

    query = Order.query

    if status:
        query = query.filter_by(status=status)

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

    return success(
        message = "Orders fetched",
        data    = {
            "orders": [o.to_dict(include_items=True) for o in paginated.items],
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
            variant = ProductVariant(
                product_id   = product.id,
                label        = v["label"].strip(),
                sku          = v.get("sku",          "").strip() or None,
                price        = float(v["price"]),
                sale_price   = float(v["sale_price"]) if v.get("sale_price") else None,
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
        image_url  : string, required
        title      : string, optional
        link_url   : string, optional
        position   : string, optional (hero/sidebar/popup)
        sort_order : int,    optional
        start_date : string, optional (YYYY-MM-DD)
        end_date   : string, optional (YYYY-MM-DD)
    """
    data = request.get_json()

    if not data or not data.get("image_url"):
        return error("image_url is required")

    banner = Banner(
        image_url  = data["image_url"].strip(),
        title      = data.get("title",      "").strip() or None,
        link_url   = data.get("link_url",   "").strip() or None,
        position   = data.get("position",   "hero"),
        sort_order = data.get("sort_order", 0),
        is_active  = data.get("is_active",  True),
        start_date = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
                     if data.get("start_date") else None,
        end_date   = datetime.strptime(data["end_date"], "%Y-%m-%d").date()
                     if data.get("end_date") else None,
    )
    db.session.add(banner)
    db.session.commit()

    return success(
        message = "Banner created",
        data    = {"banner": banner.to_dict()},
        code    = 201
    )


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

    if "title"      in data: banner.title      = data["title"].strip() or None
    if "image_url"  in data: banner.image_url  = data["image_url"].strip()
    if "link_url"   in data: banner.link_url   = data["link_url"].strip() or None
    if "position"   in data: banner.position   = data["position"]
    if "sort_order" in data: banner.sort_order = data["sort_order"]
    if "is_active"  in data: banner.is_active  = bool(data["is_active"])
    if "start_date" in data:
        banner.start_date = datetime.strptime(
            data["start_date"], "%Y-%m-%d"
        ).date() if data["start_date"] else None
    if "end_date" in data:
        banner.end_date = datetime.strptime(
            data["end_date"], "%Y-%m-%d"
        ).date() if data["end_date"] else None

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