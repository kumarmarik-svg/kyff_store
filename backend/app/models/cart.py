from datetime import datetime
from ..extensions import db


class Cart(db.Model):
    __tablename__ = "cart"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, )

    # ── Foreign Key ───────────────────────────────────────────
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        comment="NULL for guest cart"
    )

    # ── Guest Cart ────────────────────────────────────────────
    session_token = db.Column(
        db.String(255),
        nullable=True,
        comment="Random token stored in cookie for guest carts"
    )

    # ── Timestamps ────────────────────────────────────────────
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # ── Relationships ─────────────────────────────────────────
    user = db.relationship(
        "User",
        back_populates="cart"
    )

    items = db.relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    # ── Methods ───────────────────────────────────────────────
    def total_items(self):
        """Total number of individual units in cart."""
        result = db.session.query(
            db.func.sum(
                __import__('app.models.cart_item', fromlist=['CartItem']).CartItem.quantity
            )
        ).filter_by(cart_id=self.id).scalar()
        return result or 0

    def subtotal(self):
        """
        Sum of (effective_price x quantity) for all items.
        Imports CartItem and ProductVariant inline to avoid
        circular import at module level.
        """
        from .cart_item import CartItem
        from .product_variant import ProductVariant

        items = (
            db.session.query(CartItem, ProductVariant)
            .join(ProductVariant, CartItem.variant_id == ProductVariant.id)
            .filter(CartItem.cart_id == self.id)
            .all()
        )
        total = sum(
            float(item.CartItem.quantity) *
            float(item.ProductVariant.effective_price())
            for item in items
        )
        return round(total, 2)

    def is_empty(self):
        """Returns True if cart has no items."""
        return self.items.count() == 0

    def clear(self):
        """Removes all items from cart without deleting the cart itself."""
        from .cart_item import CartItem
        CartItem.query.filter_by(cart_id=self.id).delete()
        db.session.commit()

    def to_dict(self):
        return {
            "id":            self.id,
            "user_id":       self.user_id,
            "session_token": self.session_token,
            "is_empty":      self.is_empty(),
            "updated_at":    self.updated_at.isoformat(),
        }

    def __repr__(self):
        return f"<Cart {self.id} — user={self.user_id}>"