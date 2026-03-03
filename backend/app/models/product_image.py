from datetime import datetime
from ..extensions import db


class ProductImage(db.Model):
    __tablename__ = "product_images"

    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # Foreign Key
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    # Core Fields
    image_url = db.Column(
        db.String(500),
        nullable=False,
        comment="Full URL or relative path to image"
    )

    alt_text = db.Column(
        db.String(255),
        nullable=True,
        comment="Accessibility and SEO alt text"
    )

    is_primary = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="Main thumbnail shown on listing pages"
    )

    sort_order = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        comment="Display sequence in product gallery"
    )

    # Timestamp
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Relationship
    product = db.relationship(
        "Product",
        back_populates="images"
    )

    # Methods
    def to_dict(self):
        return {
            "id":         self.id,
            "product_id": self.product_id,
            "image_url":  self.image_url,
            "alt_text":   self.alt_text,
            "is_primary": self.is_primary,
            "sort_order": self.sort_order,
        }

    def __repr__(self):
        return f"<ProductImage {self.id} — product={self.product_id} primary={self.is_primary}>"