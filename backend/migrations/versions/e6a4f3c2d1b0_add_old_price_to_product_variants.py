"""Add old_price to product_variants

Stores the previous regular price so storefront can show accurate strikethrough
pricing independent of the current price field.

Revision ID: e6a4f3c2d1b0
Revises: d5f3e2b1c8a0
Create Date: 2026-03-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision      = 'e6a4f3c2d1b0'
down_revision = 'd5f3e2b1c8a0'
branch_labels = None
depends_on    = None


def upgrade():
    op.add_column(
        'product_variants',
        sa.Column('old_price', sa.Numeric(10, 2), nullable=True,
                  comment='Previous regular price before discount — shown as strikethrough')
    )
    # Back-fill: variants with an active sale_price get old_price = price
    op.execute(
        "UPDATE product_variants SET old_price = price "
        "WHERE sale_price IS NOT NULL AND old_price IS NULL"
    )


def downgrade():
    op.drop_column('product_variants', 'old_price')
