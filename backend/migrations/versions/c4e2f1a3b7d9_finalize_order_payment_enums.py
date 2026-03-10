"""Finalize order and payment status ENUMs

- orders.status: reorder values to match lifecycle
- payments.status: remove 'pending' (COD now uses 'success')

Revision ID: c4e2f1a3b7d9
Revises: b3f1c2d4e5a6
Create Date: 2026-03-10 00:00:00.000000

NOTE: MySQL stores ENUM values as 1-based integers internally.
Both ALTER statements rebuild the table mapping string values
correctly — no data loss as long as no row contains 'pending'
in payments.status before running this migration.
Run this SQL first to verify:
    SELECT COUNT(*) FROM payments WHERE status = 'pending';
"""
from alembic import op


revision      = 'c4e2f1a3b7d9'
down_revision = 'b3f1c2d4e5a6'
branch_labels = None
depends_on    = None


def upgrade():
    # ── orders.status — reorder to match lifecycle ────────────
    op.execute("""
        ALTER TABLE orders
        MODIFY status ENUM(
            'pending',
            'payment_failed',
            'confirmed',
            'processing',
            'shipped',
            'delivered',
            'cancelled',
            'expired',
            'refunded'
        ) NOT NULL DEFAULT 'pending'
    """)

    # ── payments.status — remove 'pending' (COD now uses 'success') ──
    op.execute("""
        ALTER TABLE payments
        MODIFY status ENUM(
            'initiated',
            'success',
            'failed',
            'refunded'
        ) NOT NULL DEFAULT 'initiated'
    """)


def downgrade():
    op.execute("""
        ALTER TABLE orders
        MODIFY status ENUM(
            'pending',
            'confirmed',
            'processing',
            'shipped',
            'delivered',
            'cancelled',
            'refunded',
            'payment_failed',
            'expired'
        ) NOT NULL DEFAULT 'pending'
    """)

    op.execute("""
        ALTER TABLE payments
        MODIFY status ENUM(
            'initiated',
            'pending',
            'success',
            'failed',
            'refunded'
        ) NOT NULL DEFAULT 'initiated'
    """)
