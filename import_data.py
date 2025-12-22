#!/usr/bin/env python3
"""
Data import tool for product catalog and mappings.
"""
import os
import sys
from pathlib import Path

# Add src to path if running from project root
if Path('src').exists():
    sys.path.insert(0, 'src')

from database import SchemaManager
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Import catalog and mappings data."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Import product catalog and mappings data')
    parser.add_argument('--catalog', required=True, help='Path to catalog csv file')
    parser.add_argument('--mappings', required=True, help='Path to mapping csv file')
    parser.add_argument('--db-url', help='Database URL (or use INVOICELYZER_DATABASE_URL env var)')
    
    args = parser.parse_args()
    
    # Get database URL
    db_url = args.db_url or os.getenv('INVOICELYZER_DATABASE_URL')
    if not db_url:
        logger.error("Database URL required. Use --db-url or set INVOICELYZER_DATABASE_URL")
        return 1
    
    # Check files exist
    if not Path(args.catalog).exists():
        logger.error(f"Catalog file not found: {args.catalog}")
        return 1
    
    if not Path(args.mappings).exists():
        logger.error(f"Mappings file not found: {args.mappings}")
        return 1
    
    try:
        logger.info("Initializing schema manager...")
        schema = SchemaManager(db_url)
        
        logger.info(f"\nLoading catalog from: {args.catalog}")
        catalog_count = schema.load_catalog_from_csv(args.catalog)
        logger.info(f"✓ Loaded {catalog_count} catalog products")
        
        logger.info(f"\nLoading mappings from: {args.mappings}")
        mappings_count = schema.load_mappings_from_csv(args.mappings)
        logger.info(f"✓ Loaded {mappings_count} product mappings")
        
        logger.info("\n✅ Data import complete!")
        logger.info(f"  Catalog products: {catalog_count}")
        logger.info(f"  Product mappings: {mappings_count}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Import failed: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
