"""
Product mapper for matching invoice items to catalog products.
Uses hybrid approach: known rules from database + ML fallback.
"""
import logging
import re
import math
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple
import psycopg2

logger = logging.getLogger("invoice_processor.mapper")


class ProductMapper:
    """
    Maps invoice product names to catalog products using hybrid approach.
    """
    
    def __init__(self, connection_string: str):
        """
        Initialize mapper with database connection.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self.catalog = []
        self.known_mappings = {}
        self.idf_scores = {}
        self.product_features = {}
        
        # Load data from database
        self._load_from_database()
        self._train_ml()
        
        logger.info(f"ProductMapper initialized: {len(self.catalog)} catalog items, {len(self.known_mappings)} known mappings")
    
    def _load_from_database(self):
        """Load catalog and known mappings from database."""
        try:
            with psycopg2.connect(self.connection_string) as conn:
                with conn.cursor() as cur:
                    # Load catalog
                    cur.execute("""
                        SELECT category, product_name 
                        FROM product_catalog 
                        ORDER BY category, product_name
                    """)
                    for row in cur.fetchall():
                        self.catalog.append({
                            'category': row[0],
                            'product': row[1]
                        })
                    
                    # Load known mappings
                    cur.execute("""
                        SELECT original_name, catalog_product, catalog_category, confidence
                        FROM product_mappings
                    """)
                    for row in cur.fetchall():
                        key = self._normalize_product(row[0])
                        self.known_mappings[key] = {
                            'product': row[1],
                            'category': row[2],
                            'confidence': row[3]
                        }
                    
        except Exception as e:
            logger.error(f"Failed to load mapper data: {str(e)}", exc_info=True)
            raise
    
    def _normalize_product(self, text: str) -> str:
        """Normalize product name for matching."""
        if not text:
            return ""
        
        text = text.upper().strip()
        
        # Remove common codes and units
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
        
        # Calculate IDF scores
        word_docs = defaultdict(int)
        total_docs = len(self.known_mappings)
        
        for prod_norm in self.known_mappings.keys():
            words = set(self._extract_keywords(prod_norm))
            for word in words:
                word_docs[word] += 1
        
        for word, n_docs in word_docs.items():
            self.idf_scores[word] = math.log(total_docs / (1 + n_docs))
        
        # Pre-calculate catalog features
        for item in self.catalog:
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
        """Map product using ML (fallback)."""
        features_orig = self._extract_features(original_product)
        words_orig = set(self._extract_keywords(original_product))
        
        best_score = 0
        best_match = None
        
        for item in self.catalog:
            prod_cat = item['product']
            features_cat = self.product_features.get(prod_cat, {})
            words_cat = set(self._extract_keywords(prod_cat))
            
            # TF-IDF cosine similarity
            score_tfidf = self._cosine_similarity(features_orig, features_cat)
            
            # Jaccard similarity
            if words_orig and words_cat:
                intersection = words_orig & words_cat
                union = words_orig | words_cat
                score_jaccard = len(intersection) / len(union)
            else:
                score_jaccard = 0.0
            
            # Combined score
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
            use_ml: If True, use ML as fallback
            ml_threshold: Minimum threshold to accept ML mapping
        
        Returns:
            dict with produto, categoria, confianca, score
        """
        # 1. Try exact match in known mappings
        normalized_key = self._normalize_product(original_product)
        
        if normalized_key in self.known_mappings:
            match = self.known_mappings[normalized_key]
            return {
                'product': match['product'],
                'category': match['category'],
                'confidence': 'Known',
                'score': 1.0
            }
        
        # 2. Try partial match in known mappings
        for known_key, data in self.known_mappings.items():
            if len(normalized_key) > 10 and len(known_key) > 10:
                if normalized_key in known_key or known_key in normalized_key:
                    # Check keyword overlap
                    words_orig = set(self._extract_keywords(original_product))
                    words_known = set(self._extract_keywords(known_key))
                    
                    if words_orig and words_known:
                        overlap = len(words_orig & words_known) / len(words_orig | words_known)
                        if overlap >= 0.5:  # 50% overlap
                            return {
                                'product': data['product'],
                                'category': data['category'],
                                'confidence': f'Partial({overlap:.2f})',
                                'score': overlap
                            }
        
        # 3. Use ML as fallback
        if use_ml:
            ml_result = self._map_via_ml(original_product, ml_threshold)
            if ml_result:
                return ml_result
        
        # 4. Could not map
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
            List of items with added catalog_product_name, catalog_category, mapping_confidence
        """
        logger.info(f"Mapping {len(items)} invoice items")
        
        mapped_items = []
        stats = {'known': 0, 'partial': 0, 'ml': 0, 'unknown': 0}
        
        for item in items:
            product_name = item.get('name', '')
            mapping = self.map_product(product_name, use_ml, ml_threshold)
            
            # Add mapping to item
            item['catalog_product_name'] = mapping['product']
            item['catalog_category'] = mapping['category']
            item['mapping_confidence'] = mapping['confidence']
            
            # Update stats
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
        logger.info(f"  Known: {stats['known']} ({stats['known']/total*100:.1f}%)")
        logger.info(f"  Partial: {stats['partial']} ({stats['partial']/total*100:.1f}%)")
        logger.info(f"  ML: {stats['ml']} ({stats['ml']/total*100:.1f}%)")
        logger.info(f"  Unknown: {stats['unknown']} ({stats['unknown']/total*100:.1f}%)")
        
        return mapped_items
