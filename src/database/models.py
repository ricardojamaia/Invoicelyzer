"""
SQLAlchemy ORM models for invoice database.
"""
from datetime import datetime, date, time
from typing import List, Optional
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Numeric, Date, Time, 
    DateTime, Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Invoice(Base):
    """Invoice header information."""
    __tablename__ = 'invoices'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    total: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_text_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items: Mapped[List["InvoiceItem"]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.id"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('store', 'invoice_date', 'invoice_number', name='uq_invoice_store_date_number'),
        Index('idx_invoices_store', 'store'),
        Index('idx_invoices_date', 'invoice_date'),
    )
    
    def __repr__(self):
        return f"<Invoice(id={self.id}, store={self.store}, date={self.invoice_date})>"


class InvoiceItem(Base):
    """Invoice line items."""
    __tablename__ = 'invoice_items'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(Integer, ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    catalog_product_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    catalog_category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mapping_confidence: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    days_since_last_purchase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="items")
    
    # Indexes
    __table_args__ = (
        Index('idx_items_invoice', 'invoice_id'),
        Index('idx_items_name', 'name'),
        Index('idx_items_category', 'category'),
        Index('idx_items_invoice_name', 'invoice_id', 'name'),
        Index('idx_items_catalog_product', 'catalog_product_name'),
        Index('idx_items_catalog_category', 'catalog_category'),
        Index('idx_items_catalog_product_invoice', 'catalog_product_name', 'invoice_id'),
    )
    
    def __repr__(self):
        return f"<InvoiceItem(id={self.id}, name={self.name})>"


class ProductCatalog(Base):
    """Product catalog for standardized product names."""
    __tablename__ = 'product_catalog'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    product_name: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('category', 'product_name', name='uq_catalog_category_product'),
        Index('idx_catalog_product', 'product_name'),
        Index('idx_catalog_category', 'category'),
    )
    
    def __repr__(self):
        return f"<ProductCatalog(category={self.category}, product={self.product_name})>"


class ProductMapping(Base):
    """Known mappings from invoice product names to catalog products."""
    __tablename__ = 'product_mappings'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    original_category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    catalog_product: Mapped[str] = mapped_column(String(500), nullable=False)
    catalog_category: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_mappings_original', 'original_name'),
        Index('idx_mappings_original_category', 'original_category'),
    )
    
    def __repr__(self):
        return f"<ProductMapping(original={self.original_name}, catalog={self.catalog_product})>"
