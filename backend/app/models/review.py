from datetime import datetime
from ..extensions import db


class Review(db.Model):
    __tablename__ = "reviews"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # ── Foreign Keys ──────────────────────────────────────────
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # ── Core Fields ───────────────────────────────────────────
    rating = db.Column(
        db.Integer,
        nullable=False,
        comment="1 to 5 stars"
    )

    title = db.Column(
        db.String(150),
        nullable=True
    )

    body = db.Column(
        db.Text,
        nullable=True
    )

    # ── Moderation ────────────────────────────────────────────
    is_approved = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="Admin must approve before review is visible"
    )

    # ── Timestamp ─────────────────────────────────────────────
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ── Unique Constraint ─────────────────────────────────────
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_review_user_product"
        ),
    )

    # ── Relationships ─────────────────────────────────────────
    product = db.relationship("Product", back_populates="reviews")
    user    = db.relationship("User",    back_populates="reviews")

    # ── Methods ───────────────────────────────────────────────
    def approve(self):
        self.is_approved = True

    def star_display(self):
        """Returns visual star string e.g. ★★★★☆"""
        return "★" * self.rating + "☆" * (5 - self.rating)

    def to_dict(self):
        return {
            "id":          self.id,
            "product_id":  self.product_id,
            "user_id":     self.user_id,
            "user_name":   self.user.name if self.user else "Anonymous",
            "rating":      self.rating,
            "star_display": self.star_display(),
            "title":       self.title,
            "body":        self.body,
            "is_approved": self.is_approved,
            "created_at":  self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<Review {self.id} — product={self.product_id} rating={self.rating}>"