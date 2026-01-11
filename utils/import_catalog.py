"""
Import catalog - Import product catalog and mappings from CSV files.
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from database import SchemaManager


def import_catalog(catalog_file=None, mappings_file=None):
    """
    Import product catalog and/or mappings from CSV files.
    
    Args:
        catalog_file: Path to catalog CSV file
        mappings_file: Path to mappings CSV file
    
    Returns:
        (catalog_count, mappings_count)
    """
    if not catalog_file and not mappings_file:
        raise ValueError("Must specify catalog_file and/or mappings_file")
    
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    if not db_url:
        raise ValueError("INVOICELYZER_DATABASE_URL not set")
    
    # Check files exist
    if catalog_file:
        catalog_file = Path(catalog_file)
        if not catalog_file.exists():
            raise FileNotFoundError(f"Catalog file not found: {catalog_file}")
    
    if mappings_file:
        mappings_file = Path(mappings_file)
        if not mappings_file.exists():
            raise FileNotFoundError(f"Mappings file not found: {mappings_file}")
    
    # Initialize schema manager
    schema = SchemaManager(db_url)
    
    catalog_count = 0
    mappings_count = 0
    
    # Import catalog
    if catalog_file:
        print(f"Importing catalog from: {catalog_file}")
        catalog_count = schema.load_catalog_from_csv(str(catalog_file))
        print(f"✓ Imported {catalog_count} catalog entries")
    
    # Import mappings
    if mappings_file:
        print(f"Importing mappings from: {mappings_file}")
        mappings_count = schema.load_mappings_from_csv(str(mappings_file))
        print(f"✓ Imported {mappings_count} mappings")
    
    return catalog_count, mappings_count
