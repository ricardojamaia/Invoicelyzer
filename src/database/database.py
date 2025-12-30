"""
Database operations for invoice storage and retrieval using SQLAlchemy ORM.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.orm import Session, selectinload

from .models import Invoice, InvoiceItem
from .session import SessionManager

logger = logging.getLogger("invoice_processor.database")


class InvoiceDatabase:
    """
    Handle all database operations for invoices using SQLAlchemy ORM.
    """
    
    def __init__(self, connection_string: str, echo: bool = False):
        """
        Initialize database with SQLAlchemy.
        
        Args:
            connection_string: PostgreSQL connection string
            echo: If True, log all SQL statements
        """
        self.session_manager = SessionManager(connection_string, echo=echo)
        logger.info("Initialized InvoiceDatabase with SQLAlchemy")
    
    def save_invoice(self, invoice_data: Dict) -> int:
        """
        Save or update invoice and its items.
        
        Args:
            invoice_data: Parsed invoice data dictionary
            
        Returns:
            Invoice ID from database
        """
        store = invoice_data.get('store')
        date = invoice_data.get('date')
        number = invoice_data.get('invoice_number')
        
        logger.info(f"Saving invoice: {store} - {date} - {number}")
        
        with self.session_manager.session() as session:
            # Check if invoice exists
            stmt = select(Invoice).where(
                and_(
                    Invoice.store == store,
                    Invoice.invoice_date == date,
                    Invoice.invoice_number == number
                )
            )
            existing_invoice = session.execute(stmt).scalar_one_or_none()
            
            if existing_invoice:
                logger.info(f"Invoice exists (ID: {existing_invoice.id}), updating...")
                invoice = self._update_invoice(session, existing_invoice, invoice_data)
            else:
                logger.info("Creating new invoice...")
                invoice = self._create_invoice(session, invoice_data)
            
            # Sync items
            self._sync_items(session, invoice, invoice_data.get('items', []))
            
            session.flush()  # Ensure invoice.id is available
            
            action = "Updated" if existing_invoice else "Created"
            item_count = len(invoice.items)
            logger.info(f"{action} invoice with {item_count} items (ID: {invoice.id})")
            
            return invoice.id
    
    def get_invoice(self, invoice_id: int) -> Optional[Dict]:
        """
        Retrieve invoice with all items.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            Invoice data with items, or None if not found
        """
        logger.debug(f"Retrieving invoice ID: {invoice_id}")
        
        with self.session_manager.session() as session:
            # Eager load items to avoid N+1 queries
            stmt = select(Invoice).options(
                selectinload(Invoice.items)
            ).where(Invoice.id == invoice_id)
            
            invoice = session.execute(stmt).scalar_one_or_none()
            
            if not invoice:
                logger.warning(f"Invoice not found: {invoice_id}")
                return None
            
            return self._invoice_to_dict(invoice)
    
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
        logger.info(f"Searching invoices: store={store}, date_from={date_from}, date_to={date_to}")
        
        with self.session_manager.session() as session:
            # Build query
            stmt = select(Invoice)
            
            conditions = []
            if store:
                conditions.append(Invoice.store == store)
            if date_from:
                conditions.append(Invoice.invoice_date >= date_from)
            if date_to:
                conditions.append(Invoice.invoice_date <= date_to)
            
            if conditions:
                stmt = stmt.where(and_(*conditions))
            
            stmt = stmt.order_by(Invoice.invoice_date.desc(), Invoice.id.desc()).limit(limit)
            
            invoices = session.execute(stmt).scalars().all()
            
            logger.info(f"Found {len(invoices)} invoices")
            return [self._invoice_to_dict(inv, include_items=False) for inv in invoices]
    
    def close(self):
        """Close database connections."""
        self.session_manager.close()
    
    # Private helper methods
    
    def _create_invoice(self, session: Session, invoice_data: Dict) -> Invoice:
        """Create new invoice."""
        metadata = invoice_data.get('_metadata', {})
        
        invoice = Invoice(
            store=invoice_data.get('store'),
            location=invoice_data.get('location'),
            invoice_date=invoice_data.get('date'),
            invoice_time=invoice_data.get('time'),
            total=invoice_data.get('total'),
            payment_method=invoice_data.get('payment_method'),
            invoice_number=invoice_data.get('invoice_number'),
            source_file=metadata.get('source_file'),
            raw_text_length=metadata.get('raw_text_length')
        )
        
        session.add(invoice)
        session.flush()  # Get invoice.id
        
        logger.debug(f"Created invoice (ID: {invoice.id})")
        return invoice
    
    def _update_invoice(self, session: Session, invoice: Invoice, invoice_data: Dict) -> Invoice:
        """Update existing invoice."""
        metadata = invoice_data.get('_metadata', {})
        
        invoice.location = invoice_data.get('location')
        invoice.invoice_time = invoice_data.get('time')
        invoice.total = invoice_data.get('total')
        invoice.payment_method = invoice_data.get('payment_method')
        invoice.source_file = metadata.get('source_file')
        invoice.raw_text_length = metadata.get('raw_text_length')
        invoice.updated_at = datetime.utcnow()
        
        session.flush()
        
        logger.debug(f"Updated invoice (ID: {invoice.id})")
        return invoice
    
    def _sync_items(self, session: Session, invoice: Invoice, new_items: List[Dict]):
        """
        Synchronize items:
        - Update existing items (matched by name)
        - Insert new items
        - Delete removed items
        """
        # Build mapping of existing items by name
        existing_by_name = {item.name: item for item in invoice.items}
        
        processed_items = set()
        stats = {'updated': 0, 'inserted': 0, 'deleted': 0}
        
        # Process new items
        for item_data in new_items:
            name = item_data.get('name')
            
            if name in existing_by_name:
                # Update existing item
                item = existing_by_name[name]
                
                if self._should_update_item(item, item_data):
                    self._update_item(item, item_data)
                    stats['updated'] += 1
                
                processed_items.add(item)
            else:
                # Create new item
                item = self._create_item(invoice, item_data)
                session.add(item)
                stats['inserted'] += 1
                processed_items.add(item)
        
        # Delete items no longer present
        for item in invoice.items[:]:  # Create copy to modify during iteration
            if item not in processed_items:
                session.delete(item)
                stats['deleted'] += 1
        
        if any(stats.values()):
            logger.info(f"Item sync: {stats['updated']} updated, {stats['inserted']} inserted, {stats['deleted']} deleted")
    
    def _create_item(self, invoice: Invoice, item_data: Dict) -> InvoiceItem:
        """Create new invoice item."""
        return InvoiceItem(
            invoice=invoice,
            name=item_data.get('name'),
            category=item_data.get('category'),
            quantity=item_data.get('quantity'),
            unit_price=item_data.get('unit_price'),
            total_price=item_data.get('total_price'),
            catalog_product_name=item_data.get('catalog_product_name'),
            catalog_category=item_data.get('catalog_category'),
            mapping_confidence=item_data.get('mapping_confidence')
        )
    
    def _update_item(self, item: InvoiceItem, item_data: Dict):
        """Update existing invoice item."""
        item.category = item_data.get('category')
        item.quantity = item_data.get('quantity')
        item.unit_price = item_data.get('unit_price')
        item.total_price = item_data.get('total_price')
        item.catalog_product_name = item_data.get('catalog_product_name')
        item.catalog_category = item_data.get('catalog_category')
        item.mapping_confidence = item_data.get('mapping_confidence')
        item.updated_at = datetime.utcnow()
    
    def _should_update_item(self, item: InvoiceItem, item_data: Dict) -> bool:
        """Check if item data has changed."""
        return (
            item.category != item_data.get('category') or
            item.quantity != item_data.get('quantity') or
            item.unit_price != item_data.get('unit_price') or
            item.total_price != item_data.get('total_price') or
            item.catalog_product_name != item_data.get('catalog_product_name') or
            item.catalog_category != item_data.get('catalog_category') or
            item.mapping_confidence != item_data.get('mapping_confidence')
        )
    
    def _invoice_to_dict(self, invoice: Invoice, include_items: bool = True) -> Dict:
        """Convert Invoice ORM object to dictionary."""
        result = {
            'id': invoice.id,
            'store': invoice.store,
            'location': invoice.location,
            'date': invoice.invoice_date,
            'time': invoice.invoice_time,
            'total': invoice.total,
            'payment_method': invoice.payment_method,
            'invoice_number': invoice.invoice_number,
            'source_file': invoice.source_file,
            'raw_text_length': invoice.raw_text_length,
            'created_at': invoice.created_at,
            'updated_at': invoice.updated_at
        }
        
        if include_items:
            result['items'] = [self._item_to_dict(item) for item in invoice.items]
        
        return result
    
    def _item_to_dict(self, item: InvoiceItem) -> Dict:
        """Convert InvoiceItem ORM object to dictionary."""
        return {
            'id': item.id,
            'name': item.name,
            'category': item.category,
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_price': item.total_price,
            'catalog_product_name': item.catalog_product_name,
            'catalog_category': item.catalog_category,
            'mapping_confidence': item.mapping_confidence,
            'created_at': item.created_at,
            'updated_at': item.updated_at
        }
