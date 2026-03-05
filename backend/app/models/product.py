from datetime import datetime
from ..extensions import db


class Product(db.Model):
    __tablename__ = "products"

    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, )

    # Foreign Key
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False
    )

    # Core Fields
    name        = db.Column(db.String(220), nullable=False, comment="English name")
    name_ta     = db.Column(db.String(220), nullable=True,  comment="Tamil name")
    slug        = db.Column(db.String(255), nullable=False, unique=True)
    description = db.Column(db.Text,        nullable=True)
    short_desc  = db.Column(db.String(500), nullable=True)

    # KYFF Specific
    source_info = db.Column(db.String(500), nullable=True)

    # Pricing
    base_price = db.Column(db.Numeric(10, 2), nullable=False)

    # Flags
    is_active   = db.Column(db.Boolean, nullable=False, default=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category = db.relationship("Category", back_populates="products")
    variants = db.relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan", lazy="dynamic")
    images   = db.relationship("ProductImage",   back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order", lazy="dynamic")
    reviews  = db.relationship("Review",         back_populates="product", cascade="all, delete-orphan", lazy="dynamic")

    # Methods
    # def primary_image(self):
      #  return self.images.filter_by(is_primary=True).first()
    
    def primary_image(self):
        primary = self.images.filter_by(is_primary=True).first()
        if primary:
            return primary
        # Fallback to first image
        return self.images.order_by('sort_order').first()

    def active_variants(self):
        return self.variants.filter_by(is_active=True).all()

    def average_rating(self):
        approved = self.reviews.filter_by(is_approved=True).all()
        if not approved:
            return None
        return round(sum(r.rating for r in approved) / len(approved), 1)

    def to_dict(self, include_variants=False, include_images=False):
        data = {
            "id":          self.id,
            "category_id": self.category_id,
            "name":        self.name,
            "name_ta":     self.name_ta,
            "slug":        self.slug,
            "short_desc":  self.short_desc,
            "source_info": self.source_info,
            "base_price":  float(self.base_price),
            "is_active":   self.is_active,
            "is_featured": self.is_featured,
            "created_at":  self.created_at.isoformat(),
        }
        if include_variants:
            data["variants"] = [v.to_dict() for v in self.active_variants()]
        if include_images:
            data["images"] = [i.to_dict() for i in self.images]
        return data

    def __repr__(self):
        return f"<Product {self.id} - {self.name}>"