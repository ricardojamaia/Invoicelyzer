"""
Schema manager - Database schema operations (create, delete, reset).
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from database import SchemaManager


def create_schema():
    """Create database schema (all tables)."""
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    if not db_url:
        raise ValueError("INVOICELYZER_DATABASE_URL not set")
    
    print("Creating database schema...")
    
    schema = SchemaManager(db_url)
    schema.create_schema()
    
    print("✓ Schema created")


def delete_schema():
    """Delete database schema (drop all tables)."""
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    if not db_url:
        raise ValueError("INVOICELYZER_DATABASE_URL not set")
    
    # Ask for confirmation
    confirm = input("⚠️  This will delete ALL data. Type 'yes' to confirm: ")
    if confirm != 'yes':
        print("Cancelled")
        return
    
    print("Deleting database schema...")
    
    schema = SchemaManager(db_url)
    schema.drop_schema()
    
    print("✓ Schema dropped")


def reset_schema():
    """Reset database schema (delete + create)."""
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    if not db_url:
        raise ValueError("INVOICELYZER_DATABASE_URL not set")
    
    # Ask for confirmation
    confirm = input("⚠️  This will delete ALL data and recreate tables. Type 'yes' to confirm: ")
    if confirm != 'yes':
        print("Cancelled")
        return
    
    print("Resetting database schema...")
    
    schema = SchemaManager(db_url)
    
    # Drop then create
    schema.drop_schema()
    schema.create_schema()
    
    print("✓ Schema reset")
