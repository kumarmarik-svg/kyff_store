from datetime import datetime
from ..extensions import db


class Order(db.Model):
    __tablename__ = "orders"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # ── Foreign Key ───────────────────────────────────────────
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL for guest orders"
    )

    # ── Order Identity ────────────────────────────────────────
    order_number = db.Column(
        db.String(30),
        nullable=False,
        unique=True,
        comment="Human readable ID e.g. KYFF-20240001"
    )

    # ── Address Snapshot ──────────────────────────────────────
    # Copied from addresses table at checkout time.
    # Never linked live — historical orders are immutable.
    shipping_name    = db.Column(db.String(120), nullable=False)
    shipping_phone   = db.Column(db.String(15),  nullable=False)
    shipping_line1   = db.Column(db.String(255), nullable=False)
    shipping_line2   = db.Column(db.String(255), nullable=True)
    shipping_city    = db.Column(db.String(100), nullable=False)
    shipping_state   = db.Column(db.String(100), nullable=False)
    shipping_pincode = db.Column(db.String(10),  nullable=False)

    # ── Financials ────────────────────────────────────────────
    subtotal        = db.Column(db.Numeric(10, 2), nullable=False)
    shipping_charge = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    discount_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    total           = db.Column(db.Numeric(10, 2), nullable=False)

    # ── Status ────────────────────────────────────────────────
    status = db.Column(
        db.Enum(
            "pending",
            "confirmed",
            "processing",
            "shipped",
            "delivered",
            "cancelled",
            "refunded",
            name="order_status"
        ),
        nullable=False,
        default="pending"
    )

    # ── Notes ─────────────────────────────────────────────────
    notes = db.Column(
        db.Text,
        nullable=True,
        comment="Customer delivery instructions"
    )

    # ── Timestamps ────────────────────────────────────────────
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    # ── Relationships ─────────────────────────────────────────
    user = db.relationship(
        "User",
        back_populates="orders"
    )

    items = db.relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    payments = db.relationship(
        "Payment",
        back_populates="order",
        lazy="dynamic"
    )

    # ── Methods ───────────────────────────────────────────────
    @staticmethod
    def generate_order_number():
        """
        Generates human readable order number.
        Format: KYFF-YYYYMMDD-XXXXX
        e.g.  : KYFF-20240315-00001
        Called by Flask route before inserting order.
        """
        import secrets
        from datetime import date
        date_str = date.today().strftime("%Y%m%d")
        random_part = secrets.token_hex(3).upper()
        return f"KYFF-{date_str}-{random_part}"

    def is_cancellable(self):
        """
        Order can only be cancelled before it is shipped.
        Once shipped, customer must request a return instead.
        """
        return self.status in ("pending", "confirmed", "processing")

    def is_paid(self):
        """Returns True if any payment for this order is successful."""
        from .payment import Payment
        return Payment.query.filter_by(
            order_id=self.id,
            status="success"
        ).first() is not None

    def successful_payment(self):
        """Returns the successful payment object or None."""
        from .payment import Payment
        return Payment.query.filter_by(
            order_id=self.id,
            status="success"
        ).first()

    def cancel(self):
        """
        Cancels the order and restores stock for all items.
        Raises ValueError if order cannot be cancelled.
        """
        if not self.is_cancellable():
            raise ValueError(
                f"Order {self.order_number} cannot be cancelled. "
                f"Current status: {self.status}"
            )
        from .order_item import OrderItem
        from .product_variant import ProductVariant

        for item in self.items:
            if item.variant_id:
                variant = ProductVariant.query.get(item.variant_id)
                if variant:
                    variant.restore_stock(item.quantity)

        self.status = "cancelled"

    def shipping_address(self):
        """Returns shipping address as a clean dictionary."""
        return {
            "name":    self.shipping_name,
            "phone":   self.shipping_phone,
            "line1":   self.shipping_line1,
            "line2":   self.shipping_line2,
            "city":    self.shipping_city,
            "state":   self.shipping_state,
            "pincode": self.shipping_pincode,
        }

    def to_dict(self, include_items=False):
        data = {
            "id":               self.id,
            "order_number":     self.order_number,
            "user_id":          self.user_id,
            "status":           self.status,
            "subtotal":         float(self.subtotal),
            "shipping_charge":  float(self.shipping_charge),
            "discount_amount":  float(self.discount_amount),
            "total":            float(self.total),
            "shipping_address": self.shipping_address(),
            "notes":            self.notes,
            "is_paid":          self.is_paid(),
            "is_cancellable":   self.is_cancellable(),
            "created_at":       self.created_at.isoformat(),
        }
        if include_items:
            data["items"] = [i.to_dict() for i in self.items]
        return data

    def __repr__(self):
        return f"<Order {self.order_number} — {self.status} ₹{self.total}>"