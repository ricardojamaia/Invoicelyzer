"""
Database module for invoice storage using SQLAlchemy ORM.
"""
from .models import Base, Invoice, InvoiceItem, ProductCatalog, ProductMapping
from .session import SessionManager, get_session_manager
from .database import InvoiceDatabase
from .database_product_catalog import DatabaseProductCatalog  # <-- Add this
from .schema import SchemaManager

__all__ = [
    'Base',
    'Invoice',
    'InvoiceItem',
    'ProductCatalog',
    'ProductMapping',
    'SessionManager',
    'get_session_manager',
    'InvoiceDatabase',
    'DatabaseProductCatalog',  # <-- Add this
    'SchemaManager',
]