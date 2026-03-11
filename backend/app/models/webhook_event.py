from datetime import datetime
from ..extensions import db


class WebhookEvent(db.Model):
    """
    Idempotency log for Razorpay webhook events.

    Razorpay may deliver the same event more than once (network retries,
    server restarts). Before processing any event, the webhook handler
    checks this table. If the event_id already exists, the event is
    ignored without touching Order or Payment tables.

    event_id is Razorpay's globally unique event identifier, present in
    every webhook payload as event["id"].
    """
    __tablename__ = "webhook_events"

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id   = db.Column(db.String(100), unique=True, nullable=False,
                           comment="Razorpay event['id'] — globally unique per event")
    event_type = db.Column(db.String(100), nullable=True,
                           comment="e.g. payment.captured, payment.failed, refund.processed")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<WebhookEvent {self.event_id} [{self.event_type}]>"
