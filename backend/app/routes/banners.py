from flask import Blueprint, jsonify
from datetime import date
from ..models import Banner

banners_bp = Blueprint("banners", __name__)


@banners_bp.route("/api/banners", methods=["GET"])
def public_banners():
    """
    Public endpoint — no auth required.
    Returns banners that are active and within their scheduled date window.
    Ordered by sort_order ASC.
    """
    today = date.today()

    banners = (
        Banner.query
        .filter_by(is_active=True)
        .order_by(Banner.sort_order.asc())
        .all()
    )

    visible = [
        b for b in banners
        if (b.start_date is None or today >= b.start_date)
        and (b.end_date   is None or today <= b.end_date)
    ]

    return jsonify({"banners": [b.to_dict() for b in visible]}), 200
