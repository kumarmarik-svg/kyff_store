from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import Category, Product

# ── Blueprint ─────────────────────────────────────────────────
categories_bp = Blueprint("categories", __name__, url_prefix="/api/categories")


# ── Helpers ───────────────────────────────────────────────────
def error(message, code=400):
    return jsonify({"success": False, "message": message}), code

def success(message, data=None, code=200):
    response = {"success": True, "message": message}
    if data:
        response["data"] = data
    return jsonify(response), code


# ── GET /api/categories ───────────────────────────────────────
@categories_bp.route("/", methods=["GET"])
def list_categories():
    """
    Returns all active top-level categories.
    Used for main navigation menu.

    Query params:
        include_children → true = include subcategories (default false)

    Returns:
        200 → flat list of top-level categories
    """
    include_children = request.args.get(
        "include_children", "false"
    ).lower() == "true"

    # Only top-level categories (parent_id is NULL)
    categories = (
        Category.query
        .filter_by(is_active=True, parent_id=None)
        .order_by(Category.sort_order.asc())
        .all()
    )

    return success(
        message = "Categories fetched",
        data    = {
            "categories": [
                c.to_dict(include_children=include_children)
                for c in categories
            ]
        }
    )


# ── GET /api/categories/tree ──────────────────────────────────
@categories_bp.route("/tree", methods=["GET"])
def category_tree():
    """
    Returns full category hierarchy as a tree.
    Used for sidebar navigation and category menus.

    Example response:
        Grains
          └── Millets
          └── Rice - Raw
          └── Flours
        Oils
        Personal Care

    Returns:
        200 → nested category tree
    """
    top_level = (
        Category.query
        .filter_by(is_active=True, parent_id=None)
        .order_by(Category.sort_order.asc())
        .all()
    )

    return success(
        message = "Category tree fetched",
        data    = {
            "tree": [c.to_dict(include_children=True) for c in top_level]
        }
    )


# ── GET /api/categories/<slug> ────────────────────────────────
@categories_bp.route("/<slug>", methods=["GET"])
def get_category(slug):
    """
    Returns a single category by slug with its subcategories.

    URL param:
        slug → category slug e.g. grains, millets

    Returns:
        200 → category detail with children
        404 → category not found
    """
    category = Category.query.filter_by(
        slug      = slug,
        is_active = True
    ).first()

    if not category:
        return error("Category not found", 404)

    return success(
        message = "Category fetched",
        data    = {
            "category": category.to_dict(include_children=True),
            "parent":   category.parent.to_dict() if category.parent else None
        }
    )


# ── GET /api/categories/<slug>/products ───────────────────────
@categories_bp.route("/<slug>/products", methods=["GET"])
def category_products(slug):
    """
    Returns paginated products under a category.
    Also includes products from all subcategories.

    URL param:
        slug → category slug

    Query params:
        page        → page number (default 1)
        per_page    → items per page (default 12)
        sort        → newest / price_low / price_high / name

    Returns:
        200 → products + pagination + category info
        404 → category not found
    """
    category = Category.query.filter_by(
        slug      = slug,
        is_active = True
    ).first()

    if not category:
        return error("Category not found", 404)

    page     = request.args.get("page",     1,       type=int)
    per_page = request.args.get("per_page", 12,      type=int)
    sort     = request.args.get("sort",     "newest")

    # ── Collect category IDs including children ───────────────
    # e.g. "Grains" also shows Millets, Rice, Flours products
    category_ids = [category.id]
    for child in category.children:
        category_ids.append(child.id)

    # ── Build query ───────────────────────────────────────────
    query = (
        Product.query
        .filter_by(is_active=True)
        .filter(Product.category_id.in_(category_ids))
    )

    # ── Sorting ───────────────────────────────────────────────
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
        message = f"Products in {category.name}",
        data    = {
            "category": category.to_dict(include_children=True),
            "products": [
                p.to_dict(include_images=True) for p in paginated.items
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