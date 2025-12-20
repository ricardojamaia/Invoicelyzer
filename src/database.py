import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger("invoice_processor.database")


class InvoiceDatabase:
    """
    Handle database operations for invoice storage.
    """
    
    def __init__(self, connection_string: str):
        """
        Args:
            connection_string: PostgreSQL connection string
                              Format: postgresql://user:password@host:port/database
        """
        self.connection_string = connection_string
        logger.info("Initializing database connection")
        self._verify_connection()
    
    def _verify_connection(self):
        """Verify database connection is working."""
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    version = cur.fetchone()[0]
                    logger.info(f"Connected to PostgreSQL: {version}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {str(e)}")
            raise Exception(f"Database connection failed: {str(e)}")
    
    def create_schema(self):
        """
        Create database schema for invoices and items.
        """
        logger.info("Creating database schema")
        
        schema_sql = """
        -- Invoices table
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            store VARCHAR(255) NOT NULL,
            location VARCHAR(255),
            invoice_date DATE NOT NULL,
            invoice_time TIME,
            total DECIMAL(10, 2) NOT NULL,
            payment_method VARCHAR(100),
            invoice_number VARCHAR(100),
            source_file VARCHAR(255),
            raw_text_length INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(store, invoice_date, invoice_number)
        );
        
        -- Invoice items table
        CREATE TABLE IF NOT EXISTS invoice_items (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(100),
            quantity DECIMAL(10, 3) NOT NULL,
            unit_price DECIMAL(10, 2) NOT NULL,
            total_price DECIMAL(10, 2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Create indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_invoices_store ON invoices(store);
        CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
        CREATE INDEX IF NOT EXISTS idx_invoices_store_date ON invoices(store, invoice_date);
        CREATE INDEX IF NOT EXISTS idx_items_invoice_id ON invoice_items(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_items_category ON invoice_items(category);
        CREATE INDEX IF NOT EXISTS idx_items_name ON invoice_items(name);
        """
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
                    conn.commit()
                    logger.info("Database schema created successfully")
        except Exception as e:
            logger.error(f"Failed to create schema: {str(e)}", exc_info=True)
            raise Exception(f"Schema creation failed: {str(e)}")
    
    def save_invoice(self, invoice_data: Dict) -> int:
        """
        Save invoice and its items to database.
        
        Args:
            invoice_data: Parsed invoice data dictionary
            
        Returns:
            Invoice ID from database
        """
        logger.info(f"Saving invoice to database: {invoice_data.get('store')} - {invoice_data.get('date')}")
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    # Insert invoice
                    invoice_sql = """
                    INSERT INTO invoices (
                        store, location, invoice_date, invoice_time, 
                        total, payment_method, invoice_number, 
                        source_file, raw_text_length
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (store, invoice_date, invoice_number) 
                    DO UPDATE SET
                        location = EXCLUDED.location,
                        invoice_time = EXCLUDED.invoice_time,
                        total = EXCLUDED.total,
                        payment_method = EXCLUDED.payment_method,
                        source_file = EXCLUDED.source_file,
                        raw_text_length = EXCLUDED.raw_text_length
                    RETURNING id;
                    """
                    
                    metadata = invoice_data.get('_metadata', {})
                    
                    cur.execute(invoice_sql, (
                        invoice_data.get('store'),
                        invoice_data.get('location'),
                        invoice_data.get('date'),
                        invoice_data.get('time'),
                        invoice_data.get('total'),
                        invoice_data.get('payment_method'),
                        invoice_data.get('invoice_number'),
                        metadata.get('source_file'),
                        metadata.get('raw_text_length')
                    ))
                    
                    invoice_id = cur.fetchone()[0]
                    logger.debug(f"Invoice saved with ID: {invoice_id}")
                    
                    # Delete existing items for this invoice (in case of update)
                    cur.execute("DELETE FROM invoice_items WHERE invoice_id = %s", (invoice_id,))
                    
                    # Insert items
                    items_sql = """
                    INSERT INTO invoice_items (
                        invoice_id, name, category, quantity, unit_price, total_price
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s
                    );
                    """
                    
                    items = invoice_data.get('items', [])
                    for item in items:
                        cur.execute(items_sql, (
                            invoice_id,
                            item.get('name'),
                            item.get('category'),
                            item.get('quantity'),
                            item.get('unit_price'),
                            item.get('total_price')
                        ))
                    
                    conn.commit()
                    logger.info(f"Successfully saved invoice with {len(items)} items (ID: {invoice_id})")
                    
                    return invoice_id
                    
        except psycopg2.IntegrityError as e:
            logger.error(f"Database integrity error: {str(e)}")
            raise Exception(f"Failed to save invoice: duplicate or constraint violation")
        except Exception as e:
            logger.error(f"Failed to save invoice to database: {str(e)}", exc_info=True)
            raise Exception(f"Database save failed: {str(e)}")
    
    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """
        Retrieve invoice by ID.
        
        Args:
            invoice_id: Database invoice ID
            
        Returns:
            Invoice data with items or None if not found
        """
        logger.debug(f"Retrieving invoice ID: {invoice_id}")
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get invoice
                    cur.execute("SELECT * FROM invoices WHERE id = %s", (invoice_id,))
                    invoice = cur.fetchone()
                    
                    if not invoice:
                        logger.warning(f"Invoice not found: {invoice_id}")
                        return None
                    
                    # Get items
                    cur.execute("SELECT * FROM invoice_items WHERE invoice_id = %s", (invoice_id,))
                    items = cur.fetchall()
                    
                    result = dict(invoice)
                    result['items'] = [dict(item) for item in items]
                    
                    return result
                    
        except Exception as e:
            logger.error(f"Failed to retrieve invoice: {str(e)}", exc_info=True)
            raise Exception(f"Database retrieval failed: {str(e)}")
    
    def search_invoices(
        self, 
        store: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search invoices with filters.
        
        Args:
            store: Filter by store name
            date_from: Filter from date (YYYY-MM-DD)
            date_to: Filter to date (YYYY-MM-DD)
            limit: Maximum results
            
        Returns:
            List of invoice records
        """
        logger.debug(f"Searching invoices: store={store}, date_from={date_from}, date_to={date_to}")
        
        query = "SELECT * FROM invoices WHERE 1=1"
        params = []
        
        if store:
            query += " AND store ILIKE %s"
            params.append(f"%{store}%")
        
        if date_from:
            query += " AND invoice_date >= %s"
            params.append(date_from)
        
        if date_to:
            query += " AND invoice_date <= %s"
            params.append(date_to)
        
        query += " ORDER BY invoice_date DESC, created_at DESC LIMIT %s"
        params.append(limit)
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, params)
                    results = cur.fetchall()
                    logger.info(f"Found {len(results)} invoices")
                    return [dict(row) for row in results]
                    
        except Exception as e:
            logger.error(f"Failed to search invoices: {str(e)}", exc_info=True)
            raise Exception(f"Database search failed: {str(e)}")