from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Review, Product, Order, OrderItem, ProductVariant
from ..utils.responses import error, success

# ── Blueprint ─────────────────────────────────────────────────
reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


# ── Internal: Has User Bought Product ─────────────────────────
def _has_purchased(user_id, product_id):
    """
    Checks if user has actually bought this product.
    Only verified buyers can leave reviews.
    Looks through delivered orders only.
    """
    purchased = (
        db.session.query(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(ProductVariant, ProductVariant.id == OrderItem.variant_id)
        .filter(
            Order.user_id    == user_id,
            Order.status     == "delivered",
            ProductVariant.product_id == product_id
        )
        .first()
    )
    return purchased is not None


# ── POST /api/reviews ─────────────────────────────────────────
@reviews_bp.route("/", methods=["POST"])
@jwt_required()
def add_review():
    """
    Adds a review for a product.
    Only verified buyers (delivered orders) can review.
    One review per user per product.
    Requires admin approval before going live.

    Request body (JSON):
        product_id : int,    required
        rating     : int,    required (1-5)
        title      : string, optional
        body       : string, optional

    Returns:
        201 → review submitted, pending approval
        400 → validation error / already reviewed
        403 → user has not purchased this product
        404 → product not found
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    if not data:
        return error("Request body is required")

    product_id = data.get("product_id")
    rating     = data.get("rating")
    title      = (data.get("title") or "").strip() or None
    body       = (data.get("body")  or "").strip() or None

    # ── Validate ──────────────────────────────────────────────
    if not product_id:
        return error("product_id is required")

    if rating is None:
        return error("Rating is required")

    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return error("Rating must be between 1 and 5")

    # ── Check product exists ──────────────────────────────────
    product = Product.query.filter_by(
        id        = product_id,
        is_active = True
    ).first()

    if not product:
        return error("Product not found", 404)

    # ── Check verified purchase ───────────────────────────────
    if not _has_purchased(user_id, product_id):
        return error(
            "You can only review products you have purchased and received",
            403
        )

    # ── Check duplicate review ────────────────────────────────
    existing = Review.query.filter_by(
        user_id    = user_id,
        product_id = product_id
    ).first()

    if existing:
        return error(
            "You have already reviewed this product. "
            "You can edit your existing review instead.",
            400
        )

    # ── Create review ─────────────────────────────────────────
    review = Review(
        product_id  = product_id,
        user_id     = user_id,
        rating      = rating,
        title       = title,
        body        = body,
        is_approved = False    # pending admin approval
    )
    db.session.add(review)
    db.session.commit()

    return success(
        message = "Review submitted successfully. "
                  "It will appear after admin approval.",
        data    = {"review": review.to_dict()},
        code    = 201
    )


# ── GET /api/reviews/product/<product_id> ─────────────────────
@reviews_bp.route("/product/<int:product_id>", methods=["GET"])
def get_product_reviews(product_id):
    """
    Returns approved reviews for a product.

    URL param:
        product_id → product id

    Query params:
        page     → page number (default 1)
        per_page → reviews per page (default 10)
        sort     → newest / highest / lowest (default newest)

    Returns:
        200 → reviews + rating summary
        404 → product not found
    """
    product = Product.query.filter_by(
        id        = product_id,
        is_active = True
    ).first()

    if not product:
        return error("Product not found", 404)

    page     = request.args.get("page",     1,        type=int)
    per_page = request.args.get("per_page", 10,       type=int)
    sort     = request.args.get("sort",     "newest")

    query = Review.query.filter_by(
        product_id  = product_id,
        is_approved = True
    )

    if sort == "highest":
        query = query.order_by(Review.rating.desc())
    elif sort == "lowest":
        query = query.order_by(Review.rating.asc())
    else:
        query = query.order_by(Review.created_at.desc())

    paginated = query.paginate(
        page      = page,
        per_page  = per_page,
        error_out = False
    )

    # ── Rating summary ────────────────────────────────────────
    all_approved = Review.query.filter_by(
        product_id  = product_id,
        is_approved = True
    ).all()

    rating_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in all_approved:
        rating_counts[r.rating] += 1

    total_reviews  = len(all_approved)
    average_rating = (
        round(sum(r.rating for r in all_approved) / total_reviews, 1)
        if total_reviews > 0 else None
    )

    return success(
        message = "Reviews fetched",
        data    = {
            "reviews": [r.to_dict() for r in paginated.items],
            "summary": {
                "total":          total_reviews,
                "average_rating": average_rating,
                "rating_counts":  rating_counts,
            },
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


# ── PATCH /api/reviews/<review_id> ───────────────────────────
@reviews_bp.route("/<int:review_id>", methods=["PATCH"])
@jwt_required()
def edit_review(review_id):
    """
    Edits an existing review.
    Resets approval status — admin must re-approve.
    Only the review author can edit.

    Request body (JSON):
        rating : int,    optional
        title  : string, optional
        body   : string, optional

    Returns:
        200 → review updated
        403 → not your review
        404 → review not found
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json()

    review = Review.query.get(review_id)

    if not review:
        return error("Review not found", 404)

    # ── Ownership check ───────────────────────────────────────
    if review.user_id != user_id:
        return error("You can only edit your own reviews", 403)

    # ── Update fields ─────────────────────────────────────────
    if "rating" in data:
        rating = data["rating"]
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            return error("Rating must be between 1 and 5")
        review.rating = rating

    if "title" in data:
        review.title = data["title"].strip() or None

    if "body" in data:
        review.body = data["body"].strip() or None

    # Reset approval — admin must re-approve edited review
    review.is_approved = False

    db.session.commit()

    return success(
        message = "Review updated. It will reappear after admin approval.",
        data    = {"review": review.to_dict()}
    )


# ── DELETE /api/reviews/<review_id> ──────────────────────────
@reviews_bp.route("/<int:review_id>", methods=["DELETE"])
@jwt_required()
def delete_review(review_id):
    """
    Deletes a review.
    Only the review author can delete their own review.

    Returns:
        200 → review deleted
        403 → not your review
        404 → review not found
    """
    user_id = int(get_jwt_identity())

    review = Review.query.get(review_id)

    if not review:
        return error("Review not found", 404)

    if review.user_id != user_id:
        return error("You can only delete your own reviews", 403)

    db.session.delete(review)
    db.session.commit()

    return success(message="Review deleted successfully")


# ── GET /api/reviews/my-reviews ───────────────────────────────
@reviews_bp.route("/my-reviews", methods=["GET"])
@jwt_required()
def my_reviews():
    """
    Returns all reviews written by the logged-in user.
    Shows both approved and pending reviews.

    Returns:
        200 → list of user's reviews
    """
    user_id = int(get_jwt_identity())

    reviews = (
        Review.query
        .filter_by(user_id=user_id)
        .order_by(Review.created_at.desc())
        .all()
    )

    return success(
        message = "Your reviews fetched",
        data    = {
            "reviews": [r.to_dict() for r in reviews],
            "total":   len(reviews)
        }
    )


# ── GET /api/reviews/can-review/<product_id> ─────────────────
@reviews_bp.route("/can-review/<int:product_id>", methods=["GET"])
@jwt_required()
def can_review(product_id):
    """
    Checks if logged-in user can review a product.
    Frontend uses this to show/hide the review form.

    Returns:
        200 → can_review: true/false with reason
    """
    user_id = int(get_jwt_identity())

    # Check purchased
    if not _has_purchased(user_id, product_id):
        return success(
            message = "Review eligibility checked",
            data    = {
                "can_review": False,
                "reason":     "You need to purchase and receive "
                              "this product before reviewing"
            }
        )

    # Check already reviewed
    existing = Review.query.filter_by(
        user_id    = user_id,
        product_id = product_id
    ).first()

    if existing:
        return success(
            message = "Review eligibility checked",
            data    = {
                "can_review":       False,
                "reason":           "You have already reviewed this product",
                "existing_review":  existing.to_dict()
            }
        )

    return success(
        message = "Review eligibility checked",
        data    = {
            "can_review": True,
            "reason":     "You are eligible to review this product"
        }
    )