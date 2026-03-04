from datetime import datetime, date
from ..extensions import db


class Banner(db.Model):
    __tablename__ = "banners"

    # ── Primary Key ───────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True, )

    # ── Core Fields ───────────────────────────────────────────
    title = db.Column(
        db.String(150),
        nullable=True
    )

    image_url = db.Column(
        db.String(500),
        nullable=False
    )

    link_url = db.Column(
        db.String(500),
        nullable=True,
        comment="Where banner clicks navigate to"
    )

    position = db.Column(
        db.String(60),
        nullable=False,
        default="hero",
        comment="hero, sidebar, popup"
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

    # ── Scheduling ────────────────────────────────────────────
    start_date = db.Column(
        db.Date,
        nullable=True,
        comment="Banner goes live on this date. NULL means always active."
    )

    end_date = db.Column(
        db.Date,
        nullable=True,
        comment="Banner expires on this date. NULL means no expiry."
    )

    # ── Timestamp ─────────────────────────────────────────────
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # ── Methods ───────────────────────────────────────────────
    def is_currently_active(self):
        """
        Returns True if banner is active and within
        its scheduled date range.
        Use this — not is_active alone — to decide
        whether to show a banner.
        """
        if not self.is_active:
            return False
        today = date.today()
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        return True

    def to_dict(self):
        return {
            "id":         self.id,
            "title":      self.title,
            "image_url":  self.image_url,
            "link_url":   self.link_url,
            "position":   self.position,
            "sort_order": self.sort_order,
            "is_active":  self.is_currently_active(),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date":   self.end_date.isoformat() if self.end_date else None,
        }

    def __repr__(self):
        return f"<Banner {self.id} — {self.title} [{self.position}]>"