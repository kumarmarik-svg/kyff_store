from datetime import datetime
from ..extensions import db


class ProductVariant(db.Model):
    __tablename__ = "product_variants"

    # Primary Key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # Foreign Key
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    # Core Fields
    label = db.Column(
        db.String(60),
        nullable=False,
        comment="Display label e.g. 100g, 500g, 1kg"
    )

    sku = db.Column(
        db.String(100),
        nullable=True,
        unique=True,
        comment="Stock Keeping Unit"
    )

    # Pricing
    price = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        comment="Regular price"
    )

    sale_price = db.Column(
        db.Numeric(10, 2),
        nullable=True,
        comment="Discounted price — NULL means no active sale"
    )

    # Inventory
    stock_qty = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    weight_grams = db.Column(
        db.Integer,
        nullable=True,
        comment="Physical weight for shipping calculation"
    )

    # Flag
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Timestamp
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    product = db.relationship("Product", back_populates="variants")

    cart_items = db.relationship(
        "CartItem",
        back_populates="variant",
        lazy="dynamic"
    )

    order_items = db.relationship(
        "OrderItem",
        back_populates="variant",
        lazy="dynamic"
    )

    # Methods
    def effective_price(self):
        """Returns sale_price if active, otherwise regular price.
        Always use this in cart and order calculations."""
        return self.sale_price if self.sale_price is not None else self.price

    def is_on_sale(self):
        """Returns True if this variant has an active sale price."""
        return self.sale_price is not None

    def is_in_stock(self):
        """Returns True if stock is available."""
        return self.stock_qty > 0

    def reduce_stock(self, quantity):
        """Reduces stock when an order is placed.
        Raises ValueError if insufficient stock."""
        if quantity > self.stock_qty:
            raise ValueError(
                f"Insufficient stock for '{self.label}'. "
                f"Available: {self.stock_qty}, Requested: {quantity}"
            )
        self.stock_qty -= quantity

    def restore_stock(self, quantity):
        """Restores stock when an order is cancelled."""
        self.stock_qty += quantity

    def to_dict(self):
        return {
            "id":              self.id,
            "product_id":      self.product_id,
            "label":           self.label,
            "sku":             self.sku,
            "price":           float(self.price),
            "sale_price":      float(self.sale_price) if self.sale_price else None,
            "effective_price": float(self.effective_price()),
            "is_on_sale":      self.is_on_sale(),
            "stock_qty":       self.stock_qty,
            "is_in_stock":     self.is_in_stock(),
            "weight_grams":    self.weight_grams,
            "is_active":       self.is_active,
        }

    def __repr__(self):
        return f"<ProductVariant {self.id} - {self.label}>"