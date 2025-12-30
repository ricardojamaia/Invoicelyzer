from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class ProductCatalog(ABC):
    """Abstract interface for product catalog access."""
    
    @abstractmethod
    def get_all_products(self) -> List[Dict[str, str]]:
        """Return list of {category, product_name}"""
        pass
        
    @abstractmethod
    def get_known_mapping(self, original_name: str) -> Optional[Dict[str, Optional[str]]]:
        """Return known mapping or None. Confidence may be None."""
        pass
        
    @abstractmethod
    def get_all_known_mappings(self) -> Dict[str, Dict[str, Optional[str]]]:
        """Return all known mappings. Confidence values may be None."""
        pass
    