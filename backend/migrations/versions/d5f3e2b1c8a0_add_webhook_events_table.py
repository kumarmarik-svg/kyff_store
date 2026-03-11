"""Add webhook_events table for idempotency

Prevents duplicate processing when Razorpay retries the same event.

Revision ID: d5f3e2b1c8a0
Revises: c4e2f1a3b7d9
Create Date: 2026-03-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision      = 'd5f3e2b1c8a0'
down_revision = 'c4e2f1a3b7d9'
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        'webhook_events',
        sa.Column('id',         sa.Integer(),     nullable=False, autoincrement=True),
        sa.Column('event_id',   sa.String(100),   nullable=False,
                  comment="Razorpay event['id'] — globally unique per event"),
        sa.Column('event_type', sa.String(100),   nullable=True,
                  comment="e.g. payment.captured, payment.failed, refund.processed"),
        sa.Column('created_at', sa.DateTime(),    nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', name='uq_webhook_events_event_id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )


def downgrade():
    op.drop_table('webhook_events')
