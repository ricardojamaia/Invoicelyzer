#!/usr/bin/env python3
"""
Backfill original_category in product_mappings from invoice_items.

This script looks at invoice_items to find the most common category
used for each product name, and updates the product_mappings table.

Usage:
    python backfill_original_category.py
    
Environment:
    INVOICELYZER_DATABASE_URL - PostgreSQL connection string
"""
import os
import sys
import logging
from collections import Counter
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session

# Add parent directory to path to import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SessionManager
from database.models import InvoiceItem, ProductMapping

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_most_common_category(session: Session, product_name: str) -> str:
    """
    Find the most common category for a product name in invoice_items.
    
    Args:
        session: Database session
        product_name: Product name to search for
        
    Returns:
        Most common category, or None if not found
    """
    stmt = (
        select(InvoiceItem.category, func.count(InvoiceItem.category).label('count'))
        .where(InvoiceItem.name == product_name)
        .where(InvoiceItem.category.isnot(None))
        .group_by(InvoiceItem.category)
        .order_by(func.count(InvoiceItem.category).desc())
    )
    
    result = session.execute(stmt).first()
    
    if result:
        return result[0]  # Return the category
    
    return None


def backfill_original_category(connection_string: str):
    """
    Backfill original_category for all product mappings.
    
    Args:
        connection_string: Database connection string
    """
    logger.info("Starting backfill of original_category in product_mappings")
    
    session_manager = SessionManager(connection_string, echo=False)
    
    try:
        with session_manager.session() as session:
            # Get all mappings
            stmt = select(ProductMapping)
            mappings = session.execute(stmt).scalars().all()
            
            total_mappings = len(mappings)
            logger.info(f"Found {total_mappings} product mappings to process")
            
            if total_mappings == 0:
                logger.info("No mappings to backfill")
                return
            
            updated_count = 0
            not_found_count = 0
            
            for idx, mapping in enumerate(mappings, 1):
                try:
                    # Find most common category for this product name
                    common_category = get_most_common_category(session, mapping.original_name)
                    
                    if common_category:
                        mapping.original_category = common_category
                        mapping.updated_at = datetime.utcnow()
                        updated_count += 1
                        logger.debug(f"Updated {mapping.original_name} → {common_category}")
                    else:
                        not_found_count += 1
                        logger.debug(f"No category found for {mapping.original_name}")
                    
                    # Commit periodically
                    if idx % 100 == 0:
                        session.commit()
                        logger.info(f"Progress: {idx}/{total_mappings} mappings processed")
                
                except Exception as e:
                    logger.error(f"Error processing mapping {mapping.id}: {e}")
                    continue
            
            # Final commit
            session.commit()
            
            logger.info("=" * 60)
            logger.info("Backfill complete!")
            logger.info(f"Total mappings: {total_mappings}")
            logger.info(f"Updated: {updated_count}")
            logger.info(f"No category found: {not_found_count}")
            logger.info("=" * 60)
    
    finally:
        session_manager.close()


def verify_backfill(connection_string: str):
    """
    Verify the backfill was successful.
    
    Args:
        connection_string: Database connection string
    """
    logger.info("\nVerifying backfill...")
    
    session_manager = SessionManager(connection_string, echo=False)
    
    try:
        with session_manager.session() as session:
            # Count total mappings
            total = session.query(ProductMapping).count()
            
            # Count mappings with original_category
            with_category = (
                session.query(ProductMapping)
                .filter(ProductMapping.original_category.isnot(None))
                .count()
            )
            
            # Count without original_category
            without_category = total - with_category
            
            logger.info(f"Total mappings: {total}")
            logger.info(f"With original_category: {with_category}")
            logger.info(f"Without original_category: {without_category}")
            
            if with_category > 0:
                logger.info(f"✓ Coverage: {with_category/total*100:.1f}%")
            
            # Show sample mappings
            logger.info("\nSample mappings with categories:")
            sample = (
                session.query(ProductMapping)
                .filter(ProductMapping.original_category.isnot(None))
                .limit(5)
                .all()
            )
            
            for mapping in sample:
                logger.info(f"  {mapping.original_name} ({mapping.original_category}) → "
                          f"{mapping.catalog_product} ({mapping.catalog_category})")
    
    finally:
        session_manager.close()


def main():
    """Main entry point."""
    # Get database URL
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    
    if not db_url:
        logger.error("Error: INVOICELYZER_DATABASE_URL environment variable not set")
        sys.exit(1)
    
    logger.info(f"Using database: {db_url.split('@')[1] if '@' in db_url else 'configured'}")
    
    # Confirm before proceeding
    response = input("\nThis will update product_mappings table. Continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        logger.info("Aborted by user")
        sys.exit(0)
    
    # Run backfill
    backfill_original_category(db_url)
    
    # Verify
    verify_backfill(db_url)


if __name__ == "__main__":
    main()
