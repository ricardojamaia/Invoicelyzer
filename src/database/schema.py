"""
Database schema management.
"""
import logging
import psycopg2
from . import queries

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
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    # Create tables
                    cur.execute(queries.CREATE_INVOICES_TABLE)
                    cur.execute(queries.CREATE_ITEMS_TABLE)
                    
                    # Create indexes
                    cur.execute(queries.CREATE_INDEX_INVOICES_STORE)
                    cur.execute(queries.CREATE_INDEX_INVOICES_DATE)
                    cur.execute(queries.CREATE_INDEX_ITEMS_INVOICE)
                    cur.execute(queries.CREATE_INDEX_ITEMS_NAME)
                    cur.execute(queries.CREATE_INDEX_ITEMS_CATEGORY)
                    cur.execute(queries.CREATE_INDEX_ITEMS_INVOICE_NAME)
                    
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
                    conn.commit()
                    logger.info("Database schema dropped")
                    
        except Exception as e:
            logger.error(f"Failed to drop schema: {str(e)}", exc_info=True)
            raise Exception(f"Schema drop failed: {str(e)}")
            