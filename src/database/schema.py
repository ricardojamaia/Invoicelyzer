"""
Database schema management using SQLAlchemy.
"""
import logging
import csv
from pathlib import Path

from sqlalchemy import select

from .models import Base, ProductCatalog, ProductMapping
from .session import SessionManager

logger = logging.getLogger("invoice_processor.database.schema")


class SchemaManager:
    """Manages database schema creation and data loading using SQLAlchemy."""
    
    def __init__(self, connection_string: str, echo: bool = False):
        """
        Initialize schema manager.
        
        Args:
            connection_string: PostgreSQL connection string
            echo: If True, log all SQL statements
        """
        self.session_manager = SessionManager(connection_string, echo=echo)
    
    def create_schema(self):
        """
        Create database schema if it doesn't exist.
        Idempotent - safe to run multiple times.
        
        Note: For production, use Alembic migrations instead.
        """
        logger.info("Creating database schema")
        
        try:
            self.session_manager.create_all_tables()
            logger.info("✓ Database schema created successfully")
        
        except Exception as e:
            logger.error(f"Failed to create schema: {str(e)}", exc_info=True)
            raise Exception(f"Schema creation failed: {str(e)}")
    
    def drop_schema(self):
        """
        Drop all tables. Use with caution!
        """
        logger.warning("Dropping database schema")
        
        try:
            self.session_manager.drop_all_tables()
            logger.info("✓ Database schema dropped")
        
        except Exception as e:
            logger.error(f"Failed to drop schema: {str(e)}", exc_info=True)
            raise Exception(f"Schema drop failed: {str(e)}")
    
    def load_catalog_from_csv(self, csv_path: str) -> int:
        """
        Load product catalog from CSV file.
        Expected columns: category, product
        
        Args:
            csv_path: Path to catalog CSV file
            
        Returns:
            Number of products loaded
        """
        logger.info(f"Loading product catalog from: {csv_path}")
        
        try:
            count = 0
            with self.session_manager.session() as session:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    
                    for row in reader:
                        # Check if exists
                        stmt = select(ProductCatalog).where(
                            ProductCatalog.category == row['category'],
                            ProductCatalog.product_name == row['product']
                        )
                        existing = session.execute(stmt).scalar_one_or_none()
                        
                        if not existing:
                            product = ProductCatalog(
                                category=row['category'],
                                product_name=row['product']
                            )
                            session.add(product)
                            count += 1
                
                logger.info(f"✓ Loaded {count} catalog products")
                return count
        
        except Exception as e:
            logger.error(f"Failed to load catalog: {str(e)}", exc_info=True)
            raise Exception(f"Catalog load failed: {str(e)}")
    
    def load_mappings_from_csv(self, csv_path: str) -> int:
        """
        Load known product mappings from CSV file.
        Expected columns: original_product, catalog_product, category, confidence
        Optional: original_category
        
        Args:
            csv_path: Path to mappings CSV file
            
        Returns:
            Number of mappings loaded
        """
        logger.info(f"Loading product mappings from: {csv_path}")
        
        try:
            count = 0
            with self.session_manager.session() as session:
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    
                    for row in reader:
                        # Only load if mapped
                        if not row.get('catalog_product'):
                            continue
                        
                        # Check if exists
                        stmt = select(ProductMapping).where(
                            ProductMapping.original_name == row['original_product']
                        )
                        existing = session.execute(stmt).scalar_one_or_none()
                        
                        if existing:
                            # Update existing
                            existing.original_category = row.get('original_category')
                            existing.catalog_product = row['catalog_product']
                            existing.catalog_category = row['category']
                            existing.confidence = row.get('confidence', 'Manual')
                        else:
                            # Create new
                            mapping = ProductMapping(
                                original_name=row['original_product'],
                                original_category=row.get('original_category'),
                                catalog_product=row['catalog_product'],
                                catalog_category=row['catalog_category'],
                                confidence=row.get('confidence', 'Manual')
                            )
                            session.add(mapping)
                        
                        count += 1
                
                logger.info(f"✓ Loaded {count} product mappings")
                return count
        
        except Exception as e:
            logger.error(f"Failed to load mappings: {str(e)}", exc_info=True)
            raise Exception(f"Mappings load failed: {str(e)}")
    
    def close(self):
        """Close database connections."""
        self.session_manager.close()
