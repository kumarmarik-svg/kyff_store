from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from sqlalchemy import func
from datetime import datetime, timedelta
from ..extensions import db
from ..models import (
    Product, ProductVariant, ProductImage,
    Category, User, Order, OrderItem
)

# ── Blueprint ─────────────────────────────────────────────────
products_bp = Blueprint("products", __name__, url_prefix="/api/products")


# ── Helpers ───────────────────────────────────────────────────
def error(message, code=400):
    return jsonify({"success": False, "message": message}), code

def success(message, data=None, code=200):
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code


# ── Internal: Get Trending Products ───────────────────────────
def _get_trending(limit=5):
    """
    Returns top N products by order count in last 30 days.
    Used as fallback for new/guest customers.
    """
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    trending = (
        db.session.query(
            Product,
            func.count(OrderItem.id).label("order_count")
        )
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(OrderItem, OrderItem.variant_id == ProductVariant.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Product.is_active == True,
            Order.created_at >= thirty_days_ago,
            Order.status.notin_(["cancelled", "refunded"])
        )
        .group_by(Product.id)
        .order_by(func.count(OrderItem.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            **product.to_dict(include_variants=True, include_images=True),
            "order_count": count,
            "reason":      "trending"
        }
        for product, count in trending
    ]


# ── Internal: Check Price Drop ─────────────────────────────────
def _check_price_drop(variant_id, last_paid_price):
    """
    Compares last paid price to current effective price.
    Returns price drop info dict or None.
    """
    variant = ProductVariant.query.get(variant_id)
    if not variant:
        return None

    current_price = float(variant.effective_price())
    last_price    = float(last_paid_price)

    if current_price < last_price:
        return {
            "price_drop":   True,
            "last_paid":    last_price,
            "current_price": current_price,
            "dropped_by":   round(last_price - current_price, 2),
            "drop_percent": round(((last_price - current_price) / last_price) * 100, 1)
        }
    return None


# ── Internal: Get Personal Recommendations ────────────────────
def _get_personal_recommendations(user_id, limit=5):
    """
    Returns top N frequently bought products for a user.
    Each product includes price drop info if applicable.
    Fills remaining slots with trending if history is short.
    """
    # ── Fetch user's top frequently ordered variants ───────────
    top_items = (
        db.session.query(
            OrderItem.variant_id,
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("total_qty"),
            func.max(OrderItem.unit_price).label("last_paid_price")
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.user_id == user_id,
            Order.status.notin_(["cancelled", "refunded"])
        )
        .group_by(OrderItem.variant_id)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    results      = []
    seen_product_ids = set()

    for item in top_items:
        variant = ProductVariant.query.get(item.variant_id)
        if not variant or not variant.is_active:
            continue

        product = variant.product
        if not product or not product.is_active:
            continue

        # Avoid duplicate products from different variants
        if product.id in seen_product_ids:
            continue
        seen_product_ids.add(product.id)

        # Check price drop
        price_drop = _check_price_drop(item.variant_id, item.last_paid_price)

        results.append({
            **product.to_dict(include_variants=True, include_images=True),
            "reason":          "frequently_bought",
            "times_ordered":   int(item.total_qty),
            "last_paid_price": float(item.last_paid_price),
            "price_drop":      price_drop
        })

    # ── Fill remaining slots with trending ────────────────────
    if len(results) < limit:
        remaining = limit - len(results)
        trending  = _get_trending(limit=remaining + 5)

        for t in trending:
            if t["id"] not in seen_product_ids:
                t["reason"] = "trending"
                results.append(t)
                seen_product_ids.add(t["id"])

            if len(results) >= limit:
                break

    return results[:limit]


# ── GET /api/products ─────────────────────────────────────────
@products_bp.route("/", methods=["GET"])
def list_products():
    """
    Returns paginated list of active products.

    Query params:
        page        → page number (default 1)
        per_page    → items per page (default 12)
        category    → filter by category slug
        sort        → newest / price_low / price_high / name
        featured    → true = only featured products
    """
    page     = request.args.get("page",     1,       type=int)
    per_page = request.args.get("per_page", 12,      type=int)
    category = request.args.get("category", None)
    sort     = request.args.get("sort",     "newest")
    featured = request.args.get("featured", "false").lower() == "true"

    query = Product.query.filter_by(is_active=True)

    if category:
        cat = Category.query.filter_by(slug=category, is_active=True).first()
        if not cat:
            return error("Category not found", 404)
        query = query.filter_by(category_id=cat.id)

    if featured:
        query = query.filter_by(is_featured=True)

    if sort == "price_low":
        query = query.order_by(Product.base_price.asc())
    elif sort == "price_high":
        query = query.order_by(Product.base_price.desc())
    elif sort == "name":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.created_at.desc())

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return success(
        message = "Products fetched",
        data    = {
           "products": [p.to_dict(include_variants=True, include_images=True) for p in paginated.items],
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


# ── GET /api/products/search ──────────────────────────────────
@products_bp.route("/search", methods=["GET"])
def search_products():
    """
    Searches products by name, Tamil name, description, source.

    Query params:
        q        → search term, min 2 chars (required)
        page     → page number (default 1)
        per_page → items per page (default 12)
    """
    q        = request.args.get("q",        "").strip()
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 12, type=int)

    if not q:
        return error("Search term is required")
    if len(q) < 2:
        return error("Search term must be at least 2 characters")

    search_filter = db.or_(
        Product.name.ilike(f"%{q}%"),
        Product.name_ta.ilike(f"%{q}%"),
        Product.description.ilike(f"%{q}%"),
        Product.source_info.ilike(f"%{q}%")
    )

    paginated = (
        Product.query
        .filter_by(is_active=True)
        .filter(search_filter)
        .order_by(Product.name.asc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return success(
        message = f"{paginated.total} results found for '{q}'",
        data    = {
            "query":    q,
            "products": [p.to_dict(include_variants=True, include_images=True) for p in paginated.items],
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


# ── GET /api/products/recommendations ────────────────────────
@products_bp.route("/recommendations", methods=["GET"])
def recommendations():
    """
    Returns top 5 personalized or trending products.

    Logged-in users  → personal recommendations from order history
                     → includes price drop info per product
                     → fills with trending if history is short
    Guest users      → top 5 trending products (last 30 days)

    Header (optional):
        Authorization: Bearer <access_token>
    """
    # ── Try to get user from token — optional auth ─────────────
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
    except Exception:
        pass

    if user_id:
        products = _get_personal_recommendations(int(user_id), limit=5)
        message  = "Recommended for you"
    else:
        products = _get_trending(limit=5)
        message  = "Trending products"

    return success(message=message, data={"products": products})


# ── GET /api/products/price-drops ────────────────────────────
@products_bp.route("/price-drops", methods=["GET"])
@jwt_required()
def price_drops():
    """
    Returns all products where price dropped since
    the customer's last purchase.
    Only available to logged-in users.

    Header:
        Authorization: Bearer <access_token>

    Returns:
        200 → list of products with price drop details
        401 → not logged in
    """
    user_id = int(get_jwt_identity())

    # ── Get all distinct variants user has ordered ─────────────
    purchased = (
        db.session.query(
            OrderItem.variant_id,
            func.max(OrderItem.unit_price).label("last_paid_price")
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.user_id == user_id,
            Order.status.notin_(["cancelled", "refunded"])
        )
        .group_by(OrderItem.variant_id)
        .all()
    )

    drops   = []
    seen    = set()

    for item in purchased:
        price_drop = _check_price_drop(item.variant_id, item.last_paid_price)
        if not price_drop:
            continue

        variant = ProductVariant.query.get(item.variant_id)
        if not variant:
            continue

        product = variant.product
        if not product or not product.is_active:
            continue

        # One entry per product, not per variant
        if product.id in seen:
            continue
        seen.add(product.id)

        drops.append({
            **product.to_dict(include_variants=True, include_images=True),
            "price_drop": price_drop
        })

    return success(
        message = f"{len(drops)} price drops found",
        data    = {"products": drops}
    )


# ── GET /api/products/featured ────────────────────────────────
@products_bp.route("/featured", methods=["GET"])
def featured_products():
    """
    Returns featured products for homepage.

    Query params:
        limit → max number of products (default 8)
    """
    limit = request.args.get("limit", 8, type=int)

    products = (
        Product.query
        .filter_by(is_active=True, is_featured=True)
        .order_by(Product.created_at.desc())
        .limit(limit)
        .all()
    )

    return success(
        message = "Featured products fetched",
        data    = {
            "products": [
                p.to_dict(include_variants=True, include_images=True)
                for p in products
            ]
        }
    )


# ── GET /api/products/<slug> ──────────────────────────────────
@products_bp.route("/<slug>", methods=["GET"])
def get_product(slug):
    """
    Returns full product detail by slug.
    Includes variants, images, reviews, average rating.
    """
    product = Product.query.filter_by(slug=slug, is_active=True).first()

    if not product:
        return error("Product not found", 404)

    approved_reviews = (
        product.reviews
        .filter_by(is_approved=True)
        .order_by(db.text("created_at DESC"))
        .all()
    )

    return success(
        message = "Product fetched",
        data    = {
            "product":        product.to_dict(
                                include_variants=True,
                                include_images=True
                              ),
            "category":       product.category.to_dict(),
            "reviews":        [r.to_dict() for r in approved_reviews],
            "average_rating": product.average_rating(),
            "review_count":   len(approved_reviews),
        }
    )


# ── GET /api/products/<slug>/variants ─────────────────────────
@products_bp.route("/<slug>/variants", methods=["GET"])
def get_variants(slug):
    """
    Returns all active variants for a product.
    Used when customer selects weight on product page.
    """
    product = Product.query.filter_by(slug=slug, is_active=True).first()

    if not product:
        return error("Product not found", 404)

    variants = (
        ProductVariant.query
        .filter_by(product_id=product.id, is_active=True)
        .order_by(ProductVariant.price.asc())
        .all()
    )

    return success(
        message = "Variants fetched",
        data    = {
            "product_id": product.id,
            "variants":   [v.to_dict() for v in variants]
        }
    )