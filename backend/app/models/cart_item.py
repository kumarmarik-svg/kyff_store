from datetime import datetime
from ..extensions import db


class CartItem(db.Model):
    __tablename__ = "cart_items"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # ── Foreign Keys ──────────────────────────────────────────
    cart_id = db.Column(
        db.Integer,
        db.ForeignKey("cart.id", ondelete="CASCADE"),
        nullable=False
    )

    variant_id = db.Column(
        db.Integer,
        db.ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False
    )

    # ── Core Fields ───────────────────────────────────────────
    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=1
    )

    # ── Timestamp ─────────────────────────────────────────────
    added_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ── Unique Constraint ─────────────────────────────────────
    __table_args__ = (
        db.UniqueConstraint(
            "cart_id",
            "variant_id",
            name="uq_cartitem_variant"
        ),
    )

    # ── Relationships ─────────────────────────────────────────
    cart = db.relationship(
        "Cart",
        back_populates="items"
    )

    variant = db.relationship(
        "ProductVariant",
        back_populates="cart_items"
    )

    # ── Methods ───────────────────────────────────────────────
    def line_total(self):
        """
        Price x quantity using effective price.
        Respects sale price automatically.
        """
        return round(float(self.variant.effective_price()) * self.quantity, 2)

    def increase_quantity(self, by=1):
        """
        Increase quantity by given amount.
        Checks stock before increasing.
        """
        new_qty = self.quantity + by
        if new_qty > self.variant.stock_qty:
            raise ValueError(
                f"Only {self.variant.stock_qty} units available "
                f"for '{self.variant.label}'"
            )
        self.quantity = new_qty

    def decrease_quantity(self, by=1):
        """
        Decrease quantity by given amount.
        If quantity reaches 0, item should be removed by the route.
        """
        self.quantity = max(0, self.quantity - by)

    def to_dict(self):
        return {
            "id":         self.id,
            "cart_id":    self.cart_id,
            "variant_id": self.variant_id,
            "quantity":   self.quantity,
            "line_total": self.line_total(),
            "added_at":   self.added_at.isoformat(),
            "variant":    self.variant.to_dict(),
        }

    def __repr__(self):
        return f"<CartItem {self.id} — variant={self.variant_id} qty={self.quantity}>"