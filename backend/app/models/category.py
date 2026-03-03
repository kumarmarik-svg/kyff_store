from datetime import datetime
from ..extensions import db


class Category(db.Model):
    __tablename__ = "categories"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
        unsigned=True
    )

    # ── Self-Referencing Foreign Key ──────────────────────────
    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        default=None
    )

    # ── Core Fields ───────────────────────────────────────────
    name = db.Column(
        db.String(120),
        nullable=False
    )

    name_ta = db.Column(
        db.String(120),
        nullable=True,
        comment="Tamil name"
    )

    slug = db.Column(
        db.String(140),
        nullable=False,
        unique=True
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    image_url = db.Column(
        db.String(500),
        nullable=True
    )

    sort_order = db.Column(
        db.Integer,
        nullable=False,
        default=0
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

    # ── Self-Referencing Relationships ────────────────────────
    # Parent → Children  (Grains → [Millets, Rice, Flours])
    children = db.relationship(
        "Category",
        backref=db.backref("parent", remote_side=[id]),
        lazy="dynamic"
    )

    # ── Relationship to Products ──────────────────────────────
    products = db.relationship(
        "Product",
        back_populates="category",
        lazy="dynamic"
    )

    # ── Methods ───────────────────────────────────────────────
    def is_parent(self):
        """Returns True if this category has no parent — top level."""
        return self.parent_id is None

    def has_children(self):
        """Returns True if this category has subcategories."""
        return self.children.count() > 0

    def to_dict(self, include_children=False):
        data = {
            "id":          self.id,
            "parent_id":   self.parent_id,
            "name":        self.name,
            "name_ta":     self.name_ta,
            "slug":        self.slug,
            "description": self.description,
            "image_url":   self.image_url,
            "sort_order":  self.sort_order,
            "is_active":   self.is_active,
        }
        if include_children:
            data["children"] = [c.to_dict() for c in self.children]
        return data

    def __repr__(self):
        return f"<Category {self.id} — {self.name} (parent={self.parent_id})>"