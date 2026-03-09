"""add payment_expires_at to orders

Revision ID: b3f1c2d4e5a6
Revises: 21dc21104e82
Create Date: 2026-03-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1c2d4e5a6'
down_revision = '21dc21104e82'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'orders',
        sa.Column(
            'payment_expires_at',
            sa.DateTime(),
            nullable=True,
            comment='Unpaid order auto-cancels after this time (15 min window)'
        )
    )


def downgrade():
    op.drop_column('orders', 'payment_expires_at')
