"""
Product mapper using abstract ProductCatalog interface.
"""
import logging
import re
import math
from collections import defaultdict, Counter
from typing import Dict, List, Optional

from product_catalog import ProductCatalog

logger = logging.getLogger("invoice_processor.mapper")


class ProductMapper:
    """Maps invoice product names to catalog products."""
    
    def __init__(self, catalog: ProductCatalog, use_ml: bool = True, ml_threshold: float = 0.4):
        """
        Initialize mapper with product catalog.
        
        Args:
            catalog: ProductCatalog implementation
            use_ml: Enable ML-based mapping for unknown products
            ml_threshold: Minimum confidence threshold for ML mappings
        """
        self.catalog = catalog
        self.catalog_products = []
        self.known_mappings = {}
        self.idf_scores = {}
        self.product_features = {}
        self.use_ml = use_ml
        self.ml_threshold = ml_threshold
        
        self._load_catalog_data()
        self._train_ml()
        
        logger.info(f"ProductMapper initialized: {len(self.catalog_products)} products, {len(self.known_mappings)} mappings")
        logger.info(f"  ML enabled: {use_ml}, threshold: {ml_threshold}")
    
    def _load_catalog_data(self):
        """Load product catalog and known mappings."""
        products = self.catalog.get_all_products()
        self.catalog_products = [
            {
                'category': p['category'],
                'product': p['product_name']
            }
            for p in products
        ]
        
        mappings = self.catalog.get_all_known_mappings()
        for original_name, mapping_info in mappings.items():
            key = self._normalize_product(original_name)
            self.known_mappings[key] = {
                'product': mapping_info['product_name'],
                'category': mapping_info['category'],
                'confidence': mapping_info.get('confidence', 'Known')
            }
    
    def _normalize_product(self, text: str) -> str:
        """Normalize product name for matching."""
        if not text:
            return ""
        
        text = text.upper().strip()
        
        patterns = [
            r'\bCNT\b', r'\bEMB\.?\b', r'\bKG\b', r'\bG\b', r'\bML\b', r'\bCL\b',
            r'\bLS\b', r'\bCAL\b', r'\bIGP\b', r'\bDOC\b', r'\bR0\b',
            r'\d+G\b', r'\d+KG\b', r'\d+ML\b', r'\d+CL\b', r'\d+/\d+',
            r'\*\d+', r'\bUHT\b', r'\bBIO\b', r'\bCAT\b'
        ]
        
        for pattern in patterns:
            text = re.sub(pattern, '', text)
        
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        
        return text.strip()
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract significant keywords from text."""
        text_norm = self._normalize_product(text)
        words = text_norm.split()
        
        stopwords = {
            'DE', 'DA', 'DO', 'DAS', 'DOS', 'E', 'A', 'O', 'AS', 'OS',
            'EM', 'PARA', 'COM', 'SEM', 'IS', 'VT', 'VB', 'RC', 'DET', 
            'QJ', 'I', 'UN'
        }
        
        return [w for w in words if w not in stopwords and len(w) > 1]
    
    def _train_ml(self):
        """Train ML component with known mappings."""
        if not self.known_mappings:
            logger.warning("No known mappings to train ML model")
            return
        
        word_docs = defaultdict(int)
        total_docs = len(self.known_mappings)
        
        for prod_norm in self.known_mappings.keys():
            words = set(self._extract_keywords(prod_norm))
            for word in words:
                word_docs[word] += 1
        
        for word, n_docs in word_docs.items():
            self.idf_scores[word] = math.log(total_docs / (1 + n_docs))
        
        for item in self.catalog_products:
            prod = item['product']
            self.product_features[prod] = self._extract_features(prod)
    
    def _extract_features(self, text: str) -> Dict[str, float]:
        """Extract TF-IDF features from text."""
        words = self._extract_keywords(text)
        tf = Counter(words)
        total = len(words) if words else 1
        
        features = {}
        for word, freq in tf.items():
            tf_norm = freq / total
            idf = self.idf_scores.get(word, 1.0)
            features[word] = tf_norm * idf
        
        return features
    
    def _cosine_similarity(self, features1: Dict[str, float], features2: Dict[str, float]) -> float:
        """Calculate cosine similarity between two feature vectors."""
        common_words = set(features1.keys()) & set(features2.keys())
        
        if not common_words:
            return 0.0
        
        dot_product = sum(features1[w] * features2[w] for w in common_words)
        norm1 = math.sqrt(sum(v**2 for v in features1.values()))
        norm2 = math.sqrt(sum(v**2 for v in features2.values()))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def _map_via_ml(self, original_product: str, threshold: float = 0.4) -> Optional[Dict]:
        """Map product using ML."""
        features_orig = self._extract_features(original_product)
        words_orig = set(self._extract_keywords(original_product))
        
        best_score = 0
        best_match = None
        
        for item in self.catalog_products:
            prod_cat = item['product']
            features_cat = self.product_features.get(prod_cat, {})
            words_cat = set(self._extract_keywords(prod_cat))
            
            score_tfidf = self._cosine_similarity(features_orig, features_cat)
            
            if words_orig and words_cat:
                intersection = words_orig & words_cat
                union = words_orig | words_cat
                score_jaccard = len(intersection) / len(union)
            else:
                score_jaccard = 0.0
            
            score = 0.6 * score_tfidf + 0.4 * score_jaccard
            
            if score > best_score:
                best_score = score
                best_match = item
        
        if best_score >= threshold and best_match:
            return {
                'product': best_match['product'],
                'category': best_match['category'],
                'confidence': f'ML({best_score:.2f})',
                'score': best_score
            }
        
        return None
    
    def map_product(self, original_product: str, use_ml: bool = True, ml_threshold: float = 0.4) -> Dict:
        """
        Map a product using hybrid approach.
        
        Args:
            original_product: Product name from invoice
            use_ml: Use ML as fallback
            ml_threshold: Minimum threshold for ML mapping
        
        Returns:
            Dict with product, category, confidence, score
        """
        normalized_key = self._normalize_product(original_product)
        
        if normalized_key in self.known_mappings:
            match = self.known_mappings[normalized_key]
            return {
                'product': match['product'],
                'category': match['category'],
                'confidence': 'Known',
                'score': 1.0
            }
        
        for known_key, data in self.known_mappings.items():
            if len(normalized_key) > 10 and len(known_key) > 10:
                if normalized_key in known_key or known_key in normalized_key:
                    words_orig = set(self._extract_keywords(original_product))
                    words_known = set(self._extract_keywords(known_key))
                    
                    if words_orig and words_known:
                        overlap = len(words_orig & words_known) / len(words_orig | words_known)
                        if overlap >= 0.5:
                            return {
                                'product': data['product'],
                                'category': data['category'],
                                'confidence': f'Partial({overlap:.2f})',
                                'score': overlap
                            }
        
        if use_ml:
            ml_result = self._map_via_ml(original_product, ml_threshold)
            if ml_result:
                return ml_result
        
        return {
            'product': '',
            'category': '',
            'confidence': 'Unknown',
            'score': 0.0
        }
    
    def map_invoice_items(self, items: List[Dict], use_ml: bool = True, ml_threshold: float = 0.4) -> List[Dict]:
        """
        Map all items in an invoice.
        
        Args:
            items: List of invoice items (each with 'name' field)
            use_ml: Use ML for unknown products
            ml_threshold: ML confidence threshold
            
        Returns:
            List of items with catalog_product_name, catalog_category, mapping_confidence
        """
        logger.info(f"Mapping {len(items)} invoice items")
        
        mapped_items = []
        stats = {'known': 0, 'partial': 0, 'ml': 0, 'unknown': 0}
        
        for item in items:
            product_name = item.get('name', '')
            mapping = self.map_product(product_name, use_ml, ml_threshold)
            
            item['catalog_product_name'] = mapping['product']
            item['catalog_category'] = mapping['category']
            item['mapping_confidence'] = mapping['confidence']
            
            if mapping['confidence'] == 'Known':
                stats['known'] += 1
            elif mapping['confidence'].startswith('Partial'):
                stats['partial'] += 1
            elif mapping['confidence'].startswith('ML'):
                stats['ml'] += 1
            else:
                stats['unknown'] += 1
            
            mapped_items.append(item)
        
        total = len(items)
        total_mapped = stats['known'] + stats['partial'] + stats['ml']
        
        logger.info(f"Mapping complete: {total_mapped}/{total} mapped ({total_mapped/total*100:.1f}%)")
        logger.debug(f"  Known: {stats['known']} ({stats['known']/total*100:.1f}%)")
        logger.debug(f"  Partial: {stats['partial']} ({stats['partial']/total*100:.1f}%)")
        logger.debug(f"  ML: {stats['ml']} ({stats['ml']/total*100:.1f}%)")
        logger.debug(f"  Unknown: {stats['unknown']} ({stats['unknown']/total*100:.1f}%)")
        
        return mapped_items
    
