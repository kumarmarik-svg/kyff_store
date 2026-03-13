from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from sqlalchemy import func, exists
from datetime import datetime, timedelta
from ..extensions import db
from ..models import (
    Product, ProductVariant, ProductImage,
    Category, User, Order, OrderItem, Cart, CartItem
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
    try:
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
    except Exception as e:
        current_app.logger.error(f"Trending query error: {e}")
        return []


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
    try:
        # ── Fetch user's top frequently ordered variants ───────────
        # Only select + group by variant_id to satisfy MySQL only_full_group_by.
        rows = (
            db.session.query(
                OrderItem.variant_id,
                func.sum(OrderItem.quantity).label("total_qty")
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.user_id == user_id,
                Order.status.notin_(["cancelled", "refunded"]),
                OrderItem.variant_id.isnot(None)
            )
            .group_by(OrderItem.variant_id)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )

        # Build qty lookup keyed by variant_id
        qty_by_variant = {row.variant_id: int(row.total_qty) for row in rows}

        results          = []
        seen_product_ids = set()

        for row in rows:
            try:
                variant = ProductVariant.query.get(row.variant_id)
                if not variant or not variant.is_active:
                    continue

                product = variant.product
                if not product or not product.is_active:
                    continue

                # Avoid duplicate products from different variants
                if product.id in seen_product_ids:
                    continue
                seen_product_ids.add(product.id)

                results.append({
                    **product.to_dict(include_variants=True, include_images=True),
                    "reason":        "frequently_bought",
                    "times_ordered": qty_by_variant.get(row.variant_id, 0),
                })
            except Exception:
                continue

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

    except Exception as e:
        current_app.logger.error(f"Personal recommendations error: {e}")
        return _get_trending(limit=limit)


# ── GET /api/products ─────────────────────────────────────────
@products_bp.route("/", methods=["GET"])
def list_products():
    """
    Returns paginated list of active products with full filtering.

    Query params:
        page        → page number (default 1)
        per_page    → items per page (default 12)
        category    → filter by category slug
        sort        → newest | price_asc | price_desc | name_asc
        featured    → true = only featured products
        in_stock    → true = only products with stock > 0
        sale        → true = only products with an active sale price
        min_price   → minimum variant price (inclusive)
        max_price   → maximum variant price (inclusive)
    """
    page      = request.args.get("page",      1,       type=int)
    per_page  = request.args.get("per_page",  12,      type=int)
    category  = request.args.get("category",  None)
    sort      = request.args.get("sort",      "newest")
    featured  = request.args.get("featured",  "false").lower() == "true"
    in_stock  = request.args.get("in_stock",  "false").lower() == "true"
    on_sale   = request.args.get("sale",      "false").lower() == "true"
    min_price = request.args.get("min_price", None, type=float)
    max_price = request.args.get("max_price", None, type=float)

    query = Product.query.filter_by(is_active=True)

    # ── Category ──────────────────────────────────────────────
    if category:
        cat = Category.query.filter_by(slug=category, is_active=True).first()
        if not cat:
            # Unknown slug → return empty result rather than 404
            return success(
                message = "Products fetched",
                data    = {
                    "products": [],
                    "pagination": {
                        "page": page, "per_page": per_page,
                        "total": 0, "total_pages": 0,
                        "has_next": False, "has_prev": False,
                    }
                }
            )
        query = query.filter(Product.category_id == cat.id)

    # ── Featured ──────────────────────────────────────────────
    if featured:
        query = query.filter(Product.is_featured == True)

    # ── Price range (filter by active variant price) ───────────
    if min_price is not None:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.price      >= min_price)
            )
        )
    if max_price is not None:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.price      <= max_price)
            )
        )

    # ── In-stock ──────────────────────────────────────────────
    if in_stock:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.stock_qty  >  0)
            )
        )

    # ── On sale ───────────────────────────────────────────────
    if on_sale:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.sale_price != None)
            )
        )

    # ── Sort ──────────────────────────────────────────────────
    if sort == "price_asc":
        query = query.order_by(Product.base_price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.base_price.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.name.asc())
    else:  # newest (default)
        query = query.order_by(Product.created_at.desc())

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return success(
        message = "Products fetched",
        data    = {
            "products": [
                p.to_dict(include_variants=True, include_images=True)
                for p in paginated.items
            ],
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
    Accepts the same filter/sort params as list_products.

    Query params:
        q         → search term, min 2 chars (required)
        page      → page number (default 1)
        per_page  → items per page (default 12)
        sort      → newest | price_asc | price_desc | name_asc
        in_stock  → true = only in-stock products
        sale      → true = only on-sale products
        min_price → minimum variant price
        max_price → maximum variant price
        featured  → true = only featured
    """
    q         = request.args.get("q",        "").strip()
    page      = request.args.get("page",     1,  type=int)
    per_page  = request.args.get("per_page", 12, type=int)
    sort      = request.args.get("sort",     "newest")
    featured  = request.args.get("featured", "false").lower() == "true"
    in_stock  = request.args.get("in_stock", "false").lower() == "true"
    on_sale   = request.args.get("sale",     "false").lower() == "true"
    min_price = request.args.get("min_price", None, type=float)
    max_price = request.args.get("max_price", None, type=float)

    if not q:
        return error("Search term is required")
    if len(q) < 2:
        return error("Search term must be at least 2 characters")

    query = (
        Product.query
        .filter_by(is_active=True)
        .filter(db.or_(
            Product.name.ilike(f"%{q}%"),
            Product.name_ta.ilike(f"%{q}%"),
            Product.description.ilike(f"%{q}%"),
            Product.source_info.ilike(f"%{q}%")
        ))
    )

    # ── Featured ──────────────────────────────────────────────
    if featured:
        query = query.filter(Product.is_featured == True)

    # ── Price range ───────────────────────────────────────────
    if min_price is not None:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.price      >= min_price)
            )
        )
    if max_price is not None:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.price      <= max_price)
            )
        )

    # ── In-stock ──────────────────────────────────────────────
    if in_stock:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.stock_qty  >  0)
            )
        )

    # ── On sale ───────────────────────────────────────────────
    if on_sale:
        query = query.filter(
            exists().where(
                (ProductVariant.product_id == Product.id) &
                (ProductVariant.is_active  == True) &
                (ProductVariant.sale_price != None)
            )
        )

    # ── Sort ──────────────────────────────────────────────────
    if sort == "price_asc":
        query = query.order_by(Product.base_price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.base_price.desc())
    elif sort == "name_asc":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.name.asc())  # default for search: alphabetical

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return success(
        message = f"{paginated.total} results found for '{q}'",
        data    = {
            "query":    q,
            "products": [
                p.to_dict(include_variants=True, include_images=True)
                for p in paginated.items
            ],
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
    try:
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

    except Exception as e:
        current_app.logger.error(f"Recommendations route error: {e}")
        return success(message="Trending products", data={"products": []})


# ── GET /api/products/suggest ─────────────────────────────────
@products_bp.route("/suggest", methods=["GET"])
def suggest():
    """
    "You May Also Like" recommendations for product-detail and cart pages.

    Query params:
        product_id  (int, optional) — exclude this product (product page)
        category_id (int, optional) — for category-based fallback
        context     (str)           — 'product' or 'cart'

    Auth: optional JWT.
        Logged-in + order history → personal (frequently bought)
        Otherwise                 → same-category, featured-first
    """
    product_id  = request.args.get("product_id",  type=int)
    category_id = request.args.get("category_id", type=int)

    # ── Optional auth ──────────────────────────────────────────
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            user_id = int(identity)
    except Exception:
        pass

    # ── Build exclusion list ───────────────────────────────────
    exclude_ids = []
    if product_id:
        exclude_ids.append(product_id)

    if user_id:
        cart = Cart.query.filter_by(user_id=user_id).first()
        if cart:
            for item in cart.items.all():
                if item.variant and item.variant.product_id not in exclude_ids:
                    exclude_ids.append(item.variant.product_id)

    # ── Logged-in: check order history ────────────────────────
    recommendations = []
    rec_type        = "category"

    if user_id:
        freq_rows = (
            db.session.query(
                ProductVariant.product_id,
                func.count(OrderItem.id).label("buy_count")
            )
            .join(ProductVariant, ProductVariant.id == OrderItem.variant_id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.user_id == user_id,
                Order.status.in_(["confirmed", "processing", "shipped", "delivered"]),
                OrderItem.variant_id.isnot(None),
            )
            .group_by(ProductVariant.product_id)
            .order_by(func.count(OrderItem.id).desc())
            .limit(5)
            .all()
        )

        freq_ids = [r.product_id for r in freq_rows if r.product_id not in exclude_ids]
        if freq_ids:
            prods = Product.query.filter(
                Product.id.in_(freq_ids),
                Product.is_active == True
            ).all()
            id_order = {pid: i for i, pid in enumerate(freq_ids)}
            prods.sort(key=lambda p: id_order.get(p.id, 99))
            recommendations = prods
            rec_type = "personal"

    # ── Fallback: same-category (or sitewide featured) ────────
    if len(recommendations) < 3:
        needed       = 6 - len(recommendations)
        existing_ids = exclude_ids + [p.id for p in recommendations]

        q = Product.query.filter(Product.is_active == True)
        if existing_ids:
            q = q.filter(~Product.id.in_(existing_ids))
        if category_id:
            q = q.filter(Product.category_id == category_id)

        fallback = q.order_by(
            Product.is_featured.desc(),
            Product.created_at.desc()
        ).limit(needed).all()

        recommendations += fallback
        if rec_type != "personal":
            rec_type = "category"

    # ── Serialize ──────────────────────────────────────────────
    def _fmt(p):
        variants   = p.active_variants()
        variant    = variants[0] if variants else None
        price      = float(variant.price)      if variant else float(p.base_price)
        sale_price = float(variant.sale_price) if (variant and variant.sale_price) else None
        img        = p.primary_image()
        return {
            "id":            p.id,
            "name":          p.name,
            "slug":          p.slug,
            "primary_image": img.image_url if img else "/static/images/placeholder.png",
            "price":         price,
            "sale_price":    sale_price,
            "category_name": p.category.name if p.category else "",
        }

    return success(
        message = "Suggestions",
        data    = {
            "recommendations": [_fmt(p) for p in recommendations[:6]],
            "type":            rec_type,
        }
    )


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