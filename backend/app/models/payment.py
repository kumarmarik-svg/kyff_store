from datetime import datetime
from ..extensions import db


class Payment(db.Model):
    __tablename__ = "payments"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unsigned=True)

    # ── Foreign Key ───────────────────────────────────────────
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        comment="RESTRICT — payments must never be deleted"
    )

    # ── Gateway Identity ──────────────────────────────────────
    gateway = db.Column(
        db.String(50),
        nullable=False,
        comment="razorpay, stripe, cod, upi"
    )

    gateway_order_id = db.Column(
        db.String(255),
        nullable=True,
        comment="Gateway session ID created before customer pays"
    )

    transaction_id = db.Column(
        db.String(255),
        nullable=True,
        comment="Gateway payment ID returned after success"
    )

    # ── Financials ────────────────────────────────────────────
    amount = db.Column(
        db.Numeric(10, 2),
        nullable=False
    )

    currency = db.Column(
        db.String(5),
        nullable=False,
        default="INR"
    )

    # ── Status ────────────────────────────────────────────────
    status = db.Column(
        db.Enum(
            "initiated",
            "pending",
            "success",
            "failed",
            "refunded",
            name="payment_status"
        ),
        nullable=False,
        default="initiated"
    )

    # ── Raw Gateway Response ──────────────────────────────────
    gateway_response = db.Column(
        db.JSON,
        nullable=True,
        comment="Raw webhook or callback payload from gateway"
    )

    # ── Timestamps ────────────────────────────────────────────
    paid_at = db.Column(
        db.DateTime,
        nullable=True,
        comment="Exact time payment was confirmed successful"
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ── Relationship ──────────────────────────────────────────
    order = db.relationship(
        "Order",
        back_populates="payments"
    )

    # ── Methods ───────────────────────────────────────────────
    @staticmethod
    def initiate(order_id, gateway, amount, gateway_order_id=None):
        """
        Creates a new payment record when checkout begins.
        Status starts as 'initiated' — not yet paid.

        Usage in Flask route:
            payment = Payment.initiate(
                order_id         = order.id,
                gateway          = "razorpay",
                amount           = order.total,
                gateway_order_id = razorpay_order["id"]
            )
            db.session.add(payment)
            db.session.commit()
        """
        return Payment(
            order_id         = order_id,
            gateway          = gateway,
            amount           = amount,
            gateway_order_id = gateway_order_id,
            status           = "initiated"
        )

    def mark_success(self, transaction_id, gateway_response=None):
        """
        Marks payment as successful after webhook confirmation.
        Sets paid_at to current UTC time.

        Usage in Flask webhook route:
            payment.mark_success(
                transaction_id   = razorpay_payment_id,
                gateway_response = request.json
            )
            db.session.commit()
        """
        self.status           = "success"
        self.transaction_id   = transaction_id
        self.gateway_response = gateway_response
        self.paid_at          = datetime.utcnow()

    def mark_failed(self, gateway_response=None):
        """
        Marks payment as failed.
        Gateway response stored for debugging.
        """
        self.status           = "failed"
        self.gateway_response = gateway_response

    def mark_refunded(self):
        """
        Marks payment as refunded.
        Called when order is refunded after cancellation.
        """
        self.status = "refunded"

    def is_successful(self):
        return self.status == "success"

    def is_cod(self):
        """Returns True if this is a Cash on Delivery payment."""
        return self.gateway == "cod"

    def to_dict(self):
        return {
            "id":               self.id,
            "order_id":         self.order_id,
            "gateway":          self.gateway,
            "gateway_order_id": self.gateway_order_id,
            "transaction_id":   self.transaction_id,
            "amount":           float(self.amount),
            "currency":         self.currency,
            "status":           self.status,
            "is_successful":    self.is_successful(),
            "paid_at":          self.paid_at.isoformat() if self.paid_at else None,
            "created_at":       self.created_at.isoformat(),
        }

    def __repr__(self):
        return (
            f"<Payment {self.id} — "
            f"{self.gateway} ₹{self.amount} "
            f"[{self.status}]>"
        )