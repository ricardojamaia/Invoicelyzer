"""
Database schema management with product catalog and mappings support.
"""
import logging
import csv
import psycopg2
from pathlib import Path

logger = logging.getLogger("invoice_processor.database.schema")


class SchemaManager:
    """Manages database schema creation and updates."""
    
    def __init__(self, connection_string: str):
        """
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
    
    def create_schema(self):
        """
        Create database schema if it doesn't exist.
        Idempotent - safe to run multiple times.
        """
        logger.info("Creating database schema")
        
        # Import queries from the file we just created
        from . import queries
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    # Create main tables
                    cur.execute(queries.CREATE_INVOICES_TABLE)
                    cur.execute(queries.CREATE_ITEMS_TABLE)
                    cur.execute(queries.CREATE_CATALOG_TABLE)
                    cur.execute(queries.CREATE_MAPPINGS_TABLE)
                    
                    # Create indexes
                    cur.execute(queries.CREATE_INDEX_INVOICES_STORE)
                    cur.execute(queries.CREATE_INDEX_INVOICES_DATE)
                    cur.execute(queries.CREATE_INDEX_ITEMS_INVOICE)
                    cur.execute(queries.CREATE_INDEX_ITEMS_NAME)
                    cur.execute(queries.CREATE_INDEX_ITEMS_CATEGORY)
                    cur.execute(queries.CREATE_INDEX_ITEMS_INVOICE_NAME)
                    cur.execute(queries.CREATE_INDEX_ITEMS_CATALOG_PRODUCT)
                    cur.execute(queries.CREATE_INDEX_ITEMS_CATALOG_CATEGORY)
                    cur.execute(queries.CREATE_INDEX_CATALOG_PRODUCT)
                    cur.execute(queries.CREATE_INDEX_CATALOG_CATEGORY)
                    cur.execute(queries.CREATE_INDEX_MAPPINGS_ORIGINAL)
                    
                    conn.commit()
                    logger.info("Database schema created successfully")
                    
        except Exception as e:
            logger.error(f"Failed to create schema: {str(e)}", exc_info=True)
            raise Exception(f"Schema creation failed: {str(e)}")
    
    def drop_schema(self):
        """
        Drop all tables. Use with caution!
        """
        logger.warning("Dropping database schema")
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS invoice_items CASCADE;")
                    cur.execute("DROP TABLE IF EXISTS invoices CASCADE;")
                    cur.execute("DROP TABLE IF EXISTS product_catalog CASCADE;")
                    cur.execute("DROP TABLE IF EXISTS product_mappings CASCADE;")
                    conn.commit()
                    logger.info("Database schema dropped")
                    
        except Exception as e:
            logger.error(f"Failed to drop schema: {str(e)}", exc_info=True)
            raise Exception(f"Schema drop failed: {str(e)}")
    
    def load_catalog_from_csv(self, csv_path: str) -> int:
        """
        Load product catalog from CSV file.
        Expected columns: categoria, produto
        
        Args:
            csv_path: Path to bring_catalog_pt_atualizado.csv
            
        Returns:
            Number of products loaded
        """
        logger.info(f"Loading product catalog from: {csv_path}")
        
        from . import queries
        
        try:
            count = 0
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            cur.execute(queries.INSERT_CATALOG_ITEM, (
                                row['category'],
                                row['product']
                            ))
                            count += 1
                    
                    conn.commit()
                    logger.info(f"Loaded {count} catalog products")
                    return count
                    
        except Exception as e:
            logger.error(f"Failed to load catalog: {str(e)}", exc_info=True)
            raise Exception(f"Catalog load failed: {str(e)}")
    
    def load_mappings_from_csv(self, csv_path: str) -> int:
        """
        Load known product mappings from CSV file.
        Expected columns: original_product, catalog_product, category, confidence
        
        Args:
            csv_path: Path to mapeamento_final_combinado.csv
            
        Returns:
            Number of mappings loaded
        """
        logger.info(f"Loading product mappings from: {csv_path}")
        
        from . import queries
        
        try:
            count = 0
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Only load if mapped (has catalog product)
                            if row.get('catalog_product'):
                                cur.execute(queries.INSERT_MAPPING, (
                                    row['original_product'],
                                    row['catalog_product'],
                                    row['category'],
                                    row.get('confidence', 'Manual')
                                ))
                                count += 1
                    
                    conn.commit()
                    logger.info(f"Loaded {count} product mappings")
                    return count
                    
        except Exception as e:
            logger.error(f"Failed to load mappings: {str(e)}", exc_info=True)
            raise Exception(f"Mappings load failed: {str(e)}")
