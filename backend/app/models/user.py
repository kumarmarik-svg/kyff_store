from datetime import datetime
from ..extensions import db


class User(db.Model):
    __tablename__ = "users"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        
    )

    # ── Core Fields ───────────────────────────────────────────
    name = db.Column(
        db.String(120),
        nullable=False
    )

    email = db.Column(
        db.String(180),
        nullable=False,
        unique=True
    )

    phone = db.Column(
        db.String(15),
        nullable=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.Enum("customer", "admin", name="user_role"),
        nullable=False,
        default="customer"
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
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
    reset_tokens = db.relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    addresses = db.relationship(
        "Address",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    cart = db.relationship(
        "Cart",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    orders = db.relationship(
        "Order",
        back_populates="user",
        lazy="dynamic"
    )

    reviews = db.relationship(
        "Review",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    # ── Methods ───────────────────────────────────────────────
    def is_admin(self):
        return self.role == "admin"

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "email":      self.email,
            "phone":      self.phone,
            "role":       self.role,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self):
        return f"<User {self.id} — {self.email} ({self.role})>"