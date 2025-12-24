"""
Invoice processor with proper exception hierarchy.
"""
import logging
import os
from typing import Dict, Optional

from parser import PDFTextExtractor
from analyzer import InvoiceAnalyzer
from exceptions import (
    PermanentError,
    TemporaryError,
    PDFExtractionError,
    ServiceUnavailableError,
    NetworkError,
    DatabaseError
)

logger = logging.getLogger("invoice_processor.processor")


class InvoiceProcessor:
    """
    Orchestrates the complete invoice processing pipeline.
    Uses specific exception types for permanent vs temporary failures.
    """
    
    def __init__(
        self, 
        llm_url: str, 
        model: str = "qwen2.5:14b",
        prompt_template: Optional[str] = None,
        database_url: Optional[str] = None,
        enable_mapping: bool = True,
        mapping_use_ml: bool = True,
        mapping_ml_threshold: float = 0.4
    ):
        """
        Initialize processor with configuration.
        
        Args:
            llm_url: URL of LLM API
            model: Model name to use
            prompt_template: Path to custom prompt template
            database_url: PostgreSQL connection string for product mapping
            enable_mapping: Enable product mapping
            mapping_use_ml: Use ML for product mapping
            mapping_ml_threshold: ML confidence threshold
        """
        self.extractor = PDFTextExtractor()
        self.analyzer = InvoiceAnalyzer(
            llm_url=llm_url,
            model=model,
            prompt_template=prompt_template
        )
        
        # Product mapping configuration
        self.enable_mapping = enable_mapping
        self.mapping_use_ml = mapping_use_ml
        self.mapping_ml_threshold = mapping_ml_threshold
        self.mapper = None
        
        # Initialize mapper if enabled and database available
        if self.enable_mapping and database_url:
            try:
                from mapper import ProductMapper
                self.mapper = ProductMapper(database_url)
                logger.info("Product mapper initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize product mapper: {e}")
                logger.info("Continuing without product mapping")
        elif self.enable_mapping:
            logger.warning("Product mapping enabled but no database URL provided")
        
        logger.info(f"Initialized InvoiceProcessor (mapping: {self.enable_mapping})")
    
    def process(self, pdf_path: str, context: Optional[Dict] = None) -> Dict:
        """
        Process a complete invoice from PDF to structured data.
        
        Args:
            pdf_path: Path to PDF file
            context: Optional context hints for the analyzer
            
        Returns:
            Structured invoice data with mapped products
            
        Raises:
            PDFExtractionError: If PDF cannot be read (permanent)
            ServiceUnavailableError: If LLM service is down (temporary)
            NetworkError: If network connection fails (temporary)
            PermanentError: For other permanent failures
            TemporaryError: For other temporary failures
        """
        logger.info(f"Processing invoice: {pdf_path}")
        
        # Step 1: Extract text from PDF
        logger.info("Step 1: Extracting text from PDF")
        try:
            raw_text = self.extractor.extract_text(pdf_path)
            logger.info(f"Extracted {len(raw_text)} characters")
        
        except PDFExtractionError as e:
            # All PDF extraction errors are permanent
            logger.error(f"❌ PDF extraction failed (permanent): {e}")
            raise
        
        # Step 2: Analyze with LLM
        logger.info("Step 2: Analyzing invoice with LLM")
        try:
            invoice_data = self.analyzer.analyze(raw_text, context)
            logger.info(f"Analysis complete: {len(invoice_data.get('items', []))} items extracted")
        
        except ConnectionRefusedError as e:
            # LLM service not responding - temporary
            logger.warning(f"⚠️ LLM service unavailable (temporary): {e}")
            raise ServiceUnavailableError(f"LLM service unavailable: {e}")
        
        except ConnectionError as e:
            # Network connection issue - temporary
            logger.warning(f"⚠️ Network error (temporary): {e}")
            raise NetworkError(f"Network connection failed: {e}")
        
        except TimeoutError as e:
            # Request timeout - temporary
            logger.warning(f"⚠️ Request timeout (temporary): {e}")
            raise ServiceUnavailableError(f"LLM request timed out: {e}")
        
        except Exception as e:
            # Unknown LLM error
            error_msg = str(e).lower()
            
            # Check if it's a known temporary error
            if any(word in error_msg for word in ['timeout', 'connection', 'unavailable', 'refused']):
                logger.warning(f"⚠️ LLM error (likely temporary): {e}")
                raise ServiceUnavailableError(f"LLM error: {e}")
            
            # Otherwise treat as permanent
            logger.error(f"❌ LLM analysis failed (permanent): {e}")
            raise PermanentError(f"Analysis failed: {e}")
        
        # Add metadata
        if '_metadata' not in invoice_data:
            invoice_data['_metadata'] = {}
        invoice_data['_metadata']['raw_text_length'] = len(raw_text)
        invoice_data['_metadata']['source_file'] = os.path.basename(pdf_path)
        
        # Step 3: Map products to catalog
        if self.mapper and invoice_data.get('items'):
            logger.info("Step 3: Mapping products to catalog")
            try:
                mapped_items = self.mapper.map_invoice_items(
                    invoice_data['items'],
                    use_ml=self.mapping_use_ml,
                    ml_threshold=self.mapping_ml_threshold
                )
                invoice_data['items'] = mapped_items
                
                # Add mapping stats to metadata
                total = len(mapped_items)
                mapped = sum(1 for item in mapped_items if item.get('catalog_product_name'))
                invoice_data['_metadata']['mapping_rate'] = f"{mapped}/{total} ({mapped/total*100:.1f}%)"
                
                logger.info(f"Product mapping complete: {mapped}/{total} items mapped")
            
            except Exception as e:
                # Mapping failure is not critical - continue without
                logger.error(f"Product mapping failed: {e}", exc_info=True)
                logger.info("Continuing with unmapped products")
        else:
            if not self.mapper:
                logger.debug("Product mapper not available, skipping mapping")
            else:
                logger.debug("No items to map")
        
        logger.info(f"✓ Processing complete: {pdf_path}")
        return invoice_data
