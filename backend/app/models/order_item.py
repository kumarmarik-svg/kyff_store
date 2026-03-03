from ..extensions import db


class OrderItem(db.Model):
    __tablename__ = "order_items"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # ── Foreign Keys ──────────────────────────────────────────
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False
    )

    variant_id = db.Column(
        db.Integer,
        db.ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        comment="NULL if variant was deleted after order was placed"
    )

    # ── Snapshot Fields ───────────────────────────────────────
    # These are copied at order time — never linked live.
    # Even if product is renamed or deleted, history stays correct.
    product_name = db.Column(
        db.String(220),
        nullable=False,
        comment="Product name at time of order"
    )

    variant_label = db.Column(
        db.String(60),
        nullable=False,
        comment="Variant label at time of order e.g. 500g"
    )

    unit_price = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        comment="Price paid per unit at time of order"
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    line_total = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        comment="unit_price x quantity — stored, never computed"
    )

    # ── Relationships ─────────────────────────────────────────
    order = db.relationship(
        "Order",
        back_populates="items"
    )

    variant = db.relationship(
        "ProductVariant",
        back_populates="order_items"
    )

    # ── Methods ───────────────────────────────────────────────
    @staticmethod
    def build_from_cart_item(cart_item, order_id):
        """
        Creates an OrderItem from a CartItem at checkout.
        Snapshots all fields so history is preserved forever.
        This is called for every item in the cart during checkout.

        Usage in Flask route:
            for cart_item in cart.items:
                order_item = OrderItem.build_from_cart_item(cart_item, order.id)
                db.session.add(order_item)
        """
        variant = cart_item.variant
        product = variant.product

        return OrderItem(
            order_id      = order_id,
            variant_id    = variant.id,
            product_name  = product.name,
            variant_label = variant.label,
            unit_price    = variant.effective_price(),
            quantity      = cart_item.quantity,
            line_total    = round(
                float(variant.effective_price()) * cart_item.quantity, 2
            )
        )

    def to_dict(self):
        return {
            "id":            self.id,
            "order_id":      self.order_id,
            "variant_id":    self.variant_id,
            "product_name":  self.product_name,
            "variant_label": self.variant_label,
            "unit_price":    float(self.unit_price),
            "quantity":      self.quantity,
            "line_total":    float(self.line_total),
        }

    def __repr__(self):
        return (
            f"<OrderItem {self.id} — "
            f"{self.product_name} {self.variant_label} "
            f"x{self.quantity} @ ₹{self.unit_price}>"
        )