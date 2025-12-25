"""
Abstract product catalog interface.
Defines contract for product mapping without database dependency.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class ProductCatalog(ABC):
    """
    Abstract interface for product catalog.
    
    Implementations can use database, file, API, or any other source.
    """
    
    @abstractmethod
    def get_all_products(self) -> List[Dict[str, str]]:
        """
        Get all catalog products.
        
        Returns:
            List of products, each with 'category' and 'product_name'
        """
        pass
    
    @abstractmethod
    def get_known_mapping(self, original_name: str) -> Optional[Dict[str, str]]:
        """
        Get known mapping for a product name.
        
        Args:
            original_name: Original product name from invoice
            
        Returns:
            Dict with 'product_name', 'category', 'confidence' or None
        """
        pass
    
    @abstractmethod
    def get_all_known_mappings(self) -> Dict[str, Dict[str, str]]:
        """
        Get all known mappings.
        
        Returns:
            Dict mapping normalized names to product info
        """
        pass
