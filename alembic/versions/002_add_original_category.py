"""Add original_category to product_mappings

Revision ID: 002_add_original_category
Revises: 001_add_days_since_last_purchase
Create Date: 2024-12-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_original_category'
down_revision = '001_add_days_since_last_purchase'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add original_category column and index."""
    # Add column
    op.add_column('product_mappings', 
        sa.Column('original_category', sa.String(length=255), nullable=True)
    )
    
    # Add index for performance
    op.create_index(
        'idx_mappings_original_category',
        'product_mappings',
        ['original_category'],
        unique=False
    )


def downgrade() -> None:
    """Remove original_category column and index."""
    op.drop_index('idx_mappings_original_category', table_name='product_mappings')
    op.drop_column('product_mappings', 'original_category')
