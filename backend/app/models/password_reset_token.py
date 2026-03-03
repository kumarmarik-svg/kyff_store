from datetime import datetime
from ..extensions import db


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        unsigned=True
    )

    # ── Foreign Key ───────────────────────────────────────────
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # ── Token Fields ──────────────────────────────────────────
    token = db.Column(
        db.String(255),
        nullable=False,
        unique=True
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=False
    )

    used = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    # ── Timestamp ─────────────────────────────────────────────
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ── Relationship ──────────────────────────────────────────
    user = db.relationship(
        "User",
        back_populates="reset_tokens"
    )

    # ── Methods ───────────────────────────────────────────────
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def is_valid(self):
        return not self.used and not self.is_expired()

    def __repr__(self):
        return f"<PasswordResetToken user_id={self.user_id} used={self.used}>"