from datetime import datetime
from ..extensions import db


class Address(db.Model):
    __tablename__ = "addresses"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        
    )

    # ── Foreign Key ───────────────────────────────────────────
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # ── Address Fields ────────────────────────────────────────
    full_name = db.Column(
        db.String(120),
        nullable=False
    )

    phone = db.Column(
        db.String(15),
        nullable=False
    )

    line1 = db.Column(
        db.String(255),
        nullable=False
    )

    line2 = db.Column(
        db.String(255),
        nullable=True
    )

    city = db.Column(
        db.String(100),
        nullable=False
    )

    state = db.Column(
        db.String(100),
        nullable=False
    )

    pincode = db.Column(
        db.String(10),
        nullable=False
    )

    country = db.Column(
        db.String(60),
        nullable=False,
        default="India"
    )

    is_default = db.Column(
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
        back_populates="addresses"
    )

    # ── Methods ───────────────────────────────────────────────
    def to_dict(self):
        return {
            "id":         self.id,
            "user_id":    self.user_id,
            "full_name":  self.full_name,
            "phone":      self.phone,
            "line1":      self.line1,
            "line2":      self.line2,
            "city":       self.city,
            "state":      self.state,
            "pincode":    self.pincode,
            "country":    self.country,
            "is_default": self.is_default,
        }

    def __repr__(self):
        return f"<Address {self.id} — {self.full_name}, {self.city}>"