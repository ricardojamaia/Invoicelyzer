"""Add days_since_last_purchase to invoice_items

Revision ID: 001_add_days_since_last_purchase
Revises: 
Create Date: 2024-12-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_add_days_since_last_purchase'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add days_since_last_purchase column and index."""
    # Add column
    op.add_column('invoice_items', 
        sa.Column('days_since_last_purchase', sa.Integer(), nullable=True)
    )
    
    # Add index for performance
    op.create_index(
        'idx_items_catalog_product_invoice',
        'invoice_items',
        ['catalog_product_name', 'invoice_id'],
        unique=False
    )


def downgrade() -> None:
    """Remove days_since_last_purchase column and index."""
    op.drop_index('idx_items_catalog_product_invoice', table_name='invoice_items')
    op.drop_column('invoice_items', 'days_since_last_purchase')
