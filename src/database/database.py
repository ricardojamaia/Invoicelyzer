"""
Database operations for invoice storage and retrieval with product mapping support.
"""
import logging
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("invoice_processor.database")


class InvoiceDatabase:
    """
    Handle all database operations for invoices with product mapping.
    """
    
    def __init__(self, connection_string: str):
        """
        Args:
            connection_string: PostgreSQL connection string
                             Format: postgresql://user:password@host:port/database
        """
        self.connection_string = connection_string
        logger.info("Initialized InvoiceDatabase")
    
    def save_invoice(self, invoice_data: Dict) -> int:
        """
        Save or update invoice and its items.
        
        Args:
            invoice_data: Parsed invoice data dictionary
            
        Returns:
            Invoice ID from database
        """
        from . import queries
        
        store = invoice_data.get('store')
        date = invoice_data.get('date')
        number = invoice_data.get('invoice_number')
        
        logger.info(f"Saving invoice: {store} - {date} - {number}")
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    # Check if invoice exists
                    cur.execute(queries.CHECK_INVOICE_EXISTS, (store, date, number))
                    existing = cur.fetchone()
                    
                    if existing:
                        invoice_id = existing[0]
                        logger.info(f"Invoice exists (ID: {invoice_id}), updating...")
                        self._update_invoice(cur, invoice_id, invoice_data)
                    else:
                        invoice_id = self._insert_invoice(cur, invoice_data)
                        logger.info(f"Created new invoice (ID: {invoice_id})")
                    
                    # Update items
                    self._sync_items(cur, invoice_id, invoice_data.get('items', []))
                    
                    conn.commit()
                    
                    action = "Updated" if existing else "Created"
                    item_count = len(invoice_data.get('items', []))
                    logger.info(f"{action} invoice with {item_count} items (ID: {invoice_id})")
                    
                    return invoice_id
                    
        except Exception as e:
            logger.error(f"Failed to save invoice: {str(e)}", exc_info=True)
            raise
    
    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """
        Retrieve invoice with all items.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            Invoice data with items, or None if not found
        """
        from . import queries
        
        logger.debug(f"Retrieving invoice ID: {invoice_id}")
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get invoice
                    cur.execute(queries.GET_INVOICE, (invoice_id,))
                    invoice = cur.fetchone()
                    
                    if not invoice:
                        logger.warning(f"Invoice not found: {invoice_id}")
                        return None
                    
                    # Get items
                    cur.execute(queries.GET_INVOICE_ITEMS, (invoice_id,))
                    items = cur.fetchall()
                    
                    # Convert to dict and add items
                    result = dict(invoice)
                    result['items'] = [dict(item) for item in items]
                    
                    return result
                    
        except Exception as e:
            logger.error(f"Failed to retrieve invoice: {str(e)}", exc_info=True)
            raise
    
    def search_invoices(
        self,
        store: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search for invoices with filters.
        
        Args:
            store: Filter by store name
            date_from: Start date (YYYY-MM-DD)
            date_to: End date (YYYY-MM-DD)
            limit: Maximum number of results
            
        Returns:
            List of invoice dictionaries
        """
        from . import queries
        
        logger.info(f"Searching invoices: store={store}, date_from={date_from}, date_to={date_to}")
        
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Build query dynamically
                    query = queries.SEARCH_INVOICES
                    params = []
                    
                    if store:
                        query += " AND store = %s"
                        params.append(store)
                    
                    if date_from:
                        query += " AND invoice_date >= %s"
                        params.append(date_from)
                    
                    if date_to:
                        query += " AND invoice_date <= %s"
                        params.append(date_to)
                    
                    query += " ORDER BY invoice_date DESC, id DESC LIMIT %s"
                    params.append(limit)
                    
                    cur.execute(query, params)
                    invoices = cur.fetchall()
                    
                    logger.info(f"Found {len(invoices)} invoices")
                    return [dict(inv) for inv in invoices]
                    
        except Exception as e:
            logger.error(f"Failed to search invoices: {str(e)}", exc_info=True)
            raise
    
    # Private helper methods
    
    def _insert_invoice(self, cur, invoice_data: Dict) -> int:
        """Insert new invoice and return ID."""
        from . import queries
        
        metadata = invoice_data.get('_metadata', {})
        
        cur.execute(queries.INSERT_INVOICE, (
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
        
        return cur.fetchone()[0]
    
    def _update_invoice(self, cur, invoice_id: int, invoice_data: Dict):
        """Update existing invoice."""
        from . import queries
        
        metadata = invoice_data.get('_metadata', {})
        
        cur.execute(queries.UPDATE_INVOICE, (
            invoice_data.get('location'),
            invoice_data.get('time'),
            invoice_data.get('total'),
            invoice_data.get('payment_method'),
            metadata.get('source_file'),
            metadata.get('raw_text_length'),
            invoice_id
        ))
    
    def _sync_items(self, cur, invoice_id: int, new_items: List[Dict]):
        """
        Synchronize items:
        - Update existing items (matched by name)
        - Insert new items
        - Delete removed items
        """
        from . import queries
        
        # Get existing items
        cur.execute(queries.GET_INVOICE_ITEMS, (invoice_id,))
        existing_items = cur.fetchall()
        
        # Build mapping by name
        existing_by_name = {}
        for item in existing_items:
            existing_by_name[item[1]] = {  # item[1] is name
                'id': item[0],
                'category': item[2],
                'quantity': item[3],
                'unit_price': item[4],
                'total_price': item[5],
                'catalog_product_name': item[6],
                'catalog_category': item[7],
                'mapping_confidence': item[8]
            }
        
        processed_ids = set()
        stats = {'updated': 0, 'inserted': 0, 'deleted': 0}
        
        # Process new items
        for new_item in new_items:
            name = new_item.get('name')
            
            if name in existing_by_name:
                # Update existing item
                existing = existing_by_name[name]
                
                if self._item_changed(existing, new_item):
                    cur.execute(queries.UPDATE_ITEM, (
                        new_item.get('category'),
                        new_item.get('quantity'),
                        new_item.get('unit_price'),
                        new_item.get('total_price'),
                        new_item.get('catalog_product_name'),
                        new_item.get('catalog_category'),
                        new_item.get('mapping_confidence'),
                        existing['id']
                    ))
                    stats['updated'] += 1
                
                processed_ids.add(existing['id'])
            else:
                # Insert new item
                cur.execute(queries.INSERT_ITEM, (
                    invoice_id,
                    new_item.get('name'),
                    new_item.get('category'),
                    new_item.get('quantity'),
                    new_item.get('unit_price'),
                    new_item.get('total_price'),
                    new_item.get('catalog_product_name'),
                    new_item.get('catalog_category'),
                    new_item.get('mapping_confidence')
                ))
                stats['inserted'] += 1
        
        # Delete items no longer present
        items_to_delete = [
            item['id']
            for name, item in existing_by_name.items()
            if item['id'] not in processed_ids
        ]
        
        if items_to_delete:
            cur.execute(queries.DELETE_ITEMS, (items_to_delete,))
            stats['deleted'] = len(items_to_delete)
        
        if stats['updated'] or stats['inserted'] or stats['deleted']:
            logger.info(f"Item sync: {stats['updated']} updated, {stats['inserted']} inserted, {stats['deleted']} deleted")
    
    def _item_changed(self, existing: Dict, new_item: Dict) -> bool:
        """Check if item data has changed."""
        return (
            existing['category'] != new_item.get('category') or
            existing['quantity'] != new_item.get('quantity') or
            existing['unit_price'] != new_item.get('unit_price') or
            existing['total_price'] != new_item.get('total_price') or
            existing['catalog_product_name'] != new_item.get('catalog_product_name') or
            existing['catalog_category'] != new_item.get('catalog_category') or
            existing['mapping_confidence'] != new_item.get('mapping_confidence')
        )
