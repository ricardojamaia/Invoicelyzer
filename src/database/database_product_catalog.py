"""
Database-backed product catalog implementation using SQLAlchemy ORM.
"""
import logging
from typing import List, Dict, Optional

from sqlalchemy import select

from product_catalog import ProductCatalog
from database.models import ProductCatalog as ProductCatalogModel, ProductMapping
from database.session import SessionManager

logger = logging.getLogger("invoice_processor.database_catalog")


class DatabaseProductCatalog(ProductCatalog):
    """
    Product catalog backed by PostgreSQL database using SQLAlchemy ORM.
    """
    
    def __init__(self, connection_string: str, echo: bool = False):
        """
        Initialize with database connection.
        
        Args:
            connection_string: PostgreSQL connection string
            echo: If True, log all SQL statements
        """
        self.session_manager = SessionManager(connection_string, echo=echo)
        logger.info("Initialized DatabaseProductCatalog with SQLAlchemy")
    
    def get_all_products(self) -> List[Dict[str, str]]:
        """
        Get all catalog products from database.
        
        Returns:
            List of products with 'category' and 'product_name'
        """
        try:
            with self.session_manager.session() as session:
                stmt = select(ProductCatalogModel).order_by(
                    ProductCatalogModel.category,
                    ProductCatalogModel.product_name
                )
                products = session.execute(stmt).scalars().all()
                
                result = [
                    {
                        'category': p.category,
                        'product_name': p.product_name
                    }
                    for p in products
                ]
                
                logger.debug(f"Loaded {len(result)} catalog products")
                return result
        
        except Exception as e:
            logger.error(f"Failed to load catalog products: {e}")
            return []
    
    def get_known_mapping(self, original_name: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Get known mapping from database.
        
        Args:
            original_name: Original product name
            
        Returns:
            Dict with 'product_name', 'category', 'confidence' or None
        """
        try:
            with self.session_manager.session() as session:
                stmt = select(ProductMapping).where(
                    ProductMapping.original_name == original_name
                )
                mapping = session.execute(stmt).scalar_one_or_none()
                
                if mapping:
                    return {
                        'product_name': mapping.catalog_product,
                        'category': mapping.catalog_category,
                        'confidence': mapping.confidence,
                        'original_category': mapping.original_category
                    }
                
                return None
        
        except Exception as e:
            logger.error(f"Failed to get mapping for '{original_name}': {e}")
            return None
    
    def get_all_known_mappings(self) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Get all known mappings from database.
        
        Returns:
            Dict mapping original names to product info (with optional confidence)
        """
        try:
            with self.session_manager.session() as session:
                stmt = select(ProductMapping)
                mappings_list = session.execute(stmt).scalars().all()
                
                mappings = {
                    m.original_name: {
                        'product_name': m.catalog_product,
                        'category': m.catalog_category,
                        'confidence': m.confidence,
                        'original_category': m.original_category
                    }
                    for m in mappings_list
                }
                
                logger.debug(f"Loaded {len(mappings)} known mappings")
                return mappings
        
        except Exception as e:
            logger.error(f"Failed to load known mappings: {e}")
            return {}
    
    def close(self):
        """Close database connections."""
        self.session_manager.close()
