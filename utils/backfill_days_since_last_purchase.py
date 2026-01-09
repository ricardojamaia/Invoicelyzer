#!/usr/bin/env python3
"""
Backfill days_since_last_purchase for existing invoice items.

This script calculates and populates the days_since_last_purchase field
for all existing invoice items that have a catalog_product_name.

Usage:
    python backfill_days_since_last_purchase.py
    
Environment:
    INVOICELYZER_DATABASE_URL - PostgreSQL connection string
"""
import os
import sys
import logging
from datetime import datetime

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

# Add parent directory to path to import database module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SessionManager
from database.models import Invoice, InvoiceItem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def calculate_days_since_last_purchase(
    session: Session,
    item: InvoiceItem,
    invoice: Invoice
) -> int:
    """
    Calculate days since last purchase for a specific item.
    
    Args:
        session: Database session
        item: InvoiceItem to calculate for
        invoice: Associated Invoice
        
    Returns:
        Days since last purchase, or None if first purchase
    """
    stmt = (
        select(func.max(Invoice.invoice_date))
        .join(InvoiceItem, InvoiceItem.invoice_id == Invoice.id)
        .where(
            and_(
                InvoiceItem.catalog_product_name == item.catalog_product_name,
                Invoice.invoice_date < invoice.invoice_date
            )
        )
    )
    
    last_date = session.execute(stmt).scalar_one_or_none()
    
    if last_date:
        return (invoice.invoice_date - last_date).days
    
    return None  # First purchase


def backfill_days_since_last_purchase(connection_string: str, batch_size: int = 100):
    """
    Backfill days_since_last_purchase for all items with catalog products.
    
    Args:
        connection_string: Database connection string
        batch_size: Number of items to process per batch
    """
    logger.info("Starting backfill of days_since_last_purchase")
    
    session_manager = SessionManager(connection_string, echo=False)
    
    try:
        with session_manager.session() as session:
            # Get all items with catalog products, ordered by invoice date
            stmt = (
                select(InvoiceItem, Invoice)
                .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
                .where(InvoiceItem.catalog_product_name.isnot(None))
                .order_by(Invoice.invoice_date.asc(), InvoiceItem.id.asc())
            )
            
            results = session.execute(stmt).all()
            total_items = len(results)
            
            logger.info(f"Found {total_items} items to process")
            
            if total_items == 0:
                logger.info("No items to backfill")
                return
            
            updated_count = 0
            skipped_count = 0
            
            for idx, (item, invoice) in enumerate(results, 1):
                try:
                    # Calculate days since last purchase
                    days_since = calculate_days_since_last_purchase(session, item, invoice)
                    
                    # Update item
                    item.days_since_last_purchase = days_since
                    item.updated_at = datetime.utcnow()
                    
                    updated_count += 1
                    
                    # Commit in batches
                    if idx % batch_size == 0:
                        session.commit()
                        logger.info(f"Progress: {idx}/{total_items} items processed")
                
                except Exception as e:
                    logger.error(f"Error processing item {item.id}: {e}")
                    skipped_count += 1
                    continue
            
            # Final commit
            session.commit()
            
            logger.info("=" * 60)
            logger.info("Backfill complete!")
            logger.info(f"Total items: {total_items}")
            logger.info(f"Updated: {updated_count}")
            logger.info(f"Skipped (errors): {skipped_count}")
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
            # Count items with catalog products
            total_with_catalog = (
                session.query(InvoiceItem)
                .filter(InvoiceItem.catalog_product_name.isnot(None))
                .count()
            )
            
            # Count items with days_since_last_purchase filled
            filled = (
                session.query(InvoiceItem)
                .filter(
                    and_(
                        InvoiceItem.catalog_product_name.isnot(None),
                        InvoiceItem.days_since_last_purchase.isnot(None)
                    )
                )
                .count()
            )
            
            # Count first purchases (NULL days_since)
            first_purchases = (
                session.query(InvoiceItem)
                .filter(
                    and_(
                        InvoiceItem.catalog_product_name.isnot(None),
                        InvoiceItem.days_since_last_purchase.is_(None)
                    )
                )
                .count()
            )
            
            logger.info(f"Items with catalog products: {total_with_catalog}")
            logger.info(f"Items with days_since filled: {filled}")
            logger.info(f"First purchases (NULL): {first_purchases}")
            
            if filled + first_purchases == total_with_catalog:
                logger.info("✓ Verification passed!")
            else:
                logger.warning("⚠ Some items may not have been processed correctly")
    
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
    response = input("\nThis will update existing data. Continue? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        logger.info("Aborted by user")
        sys.exit(0)
    
    # Run backfill
    backfill_days_since_last_purchase(db_url)
    
    # Verify
    verify_backfill(db_url)


if __name__ == "__main__":
    main()
