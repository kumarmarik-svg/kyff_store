from datetime import datetime
from ..extensions import db


class ShippingRule(db.Model):
    __tablename__ = "shipping_rules"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # ── Core Fields ───────────────────────────────────────────
    name = db.Column(
        db.String(100),
        nullable=False,
        comment="e.g. Free Shipping, Standard Delivery"
    )

    min_order_value = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=0.00,
        comment="Minimum cart total to qualify for this rule"
    )

    charge = db.Column(
        db.Numeric(10, 2),
        nullable=False,
        default=0.00,
        comment="Shipping fee. 0.00 means free shipping."
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    # ── Timestamp ─────────────────────────────────────────────
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ── Methods ───────────────────────────────────────────────
    @staticmethod
    def get_charge_for(order_total):
        """
        Returns the shipping charge for a given order total.
        Picks the best matching rule — highest min_order_value
        that the order qualifies for.

        Usage in Flask checkout route:
            charge = ShippingRule.get_charge_for(cart.subtotal())
            # charge = 0.00  if order total >= 500
            # charge = 60.00 if order total < 500

        Always returns 0.00 if no active rules exist.
        """
        rule = (
            ShippingRule.query
            .filter(
                ShippingRule.is_active == True,
                ShippingRule.min_order_value <= order_total
            )
            .order_by(ShippingRule.min_order_value.desc())
            .first()
        )
        return float(rule.charge) if rule else 0.00

    def is_free(self):
        """Returns True if this rule gives free shipping."""
        return float(self.charge) == 0.00

    def to_dict(self):
        return {
            "id":               self.id,
            "name":             self.name,
            "min_order_value":  float(self.min_order_value),
            "charge":           float(self.charge),
            "is_free":          self.is_free(),
            "is_active":        self.is_active,
        }

    def __repr__(self):
        return f"<ShippingRule {self.id} — {self.name} ₹{self.charge}>"