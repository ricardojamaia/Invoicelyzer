"""
Database-backed product catalog implementation.
"""
import logging
from typing import List, Dict, Optional
import psycopg2

from product_catalog import ProductCatalog

logger = logging.getLogger("invoice_processor.database_catalog")


class DatabaseProductCatalog(ProductCatalog):
    """
    Product catalog backed by PostgreSQL database.
    """
    
    def __init__(self, connection_string: str):
        """
        Initialize with database connection.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        logger.info("Initialized DatabaseProductCatalog")
    
    def get_all_products(self) -> List[Dict[str, str]]:
        """
        Get all catalog products from database.
        
        Returns:
            List of products with 'category' and 'product_name'
        """
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT category, product_name 
                        FROM product_catalog 
                        ORDER BY category, product_name
                    """)
                    
                    products = []
                    for row in cur.fetchall():
                        products.append({
                            'category': row[0],
                            'product_name': row[1]
                        })
                    
                    logger.debug(f"Loaded {len(products)} catalog products")
                    return products
        
        except Exception as e:
            logger.error(f"Failed to load catalog products: {e}")
            return []
    
    def get_known_mapping(self, original_name: str) -> Optional[Dict[str, str]]:
        """
        Get known mapping from database.
        
        Args:
            original_name: Original product name (will be normalized)
            
        Returns:
            Dict with 'product_name', 'category', 'confidence' or None
        """
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT catalog_product, catalog_category, confidence
                        FROM product_mappings
                        WHERE original_name = %s
                    """, (original_name,))
                    
                    row = cur.fetchone()
                    if row:
                        return {
                            'product_name': row[0],
                            'category': row[1],
                            'confidence': row[2]
                        }
                    
                    return None
        
        except Exception as e:
            logger.error(f"Failed to get mapping for '{original_name}': {e}")
            return None
    
    def get_all_known_mappings(self) -> Dict[str, Dict[str, str]]:
        """
        Get all known mappings from database.
        
        Returns:
            Dict mapping original names to product info
        """
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT original_name, catalog_product, catalog_category, confidence
                        FROM product_mappings
                    """)
                    
                    mappings = {}
                    for row in cur.fetchall():
                        mappings[row[0]] = {
                            'product_name': row[1],
                            'category': row[2],
                            'confidence': row[3]
                        }
                    
                    logger.debug(f"Loaded {len(mappings)} known mappings")
                    return mappings
        
        except Exception as e:
            logger.error(f"Failed to load known mappings: {e}")
            return {}
        