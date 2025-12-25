"""
Invoice processor - orchestrates the complete processing pipeline.
"""
import logging
import os
from typing import Dict, Optional
from pathlib import Path

from parser import PDFTextExtractor
from analyzer import InvoiceAnalyzer
from mapper import ProductMapper
from exceptions import (
    PermanentError,
    TemporaryError,
    PDFExtractionError
)

logger = logging.getLogger("invoice_processor.processor")


class InvoiceProcessor:
    """
    Orchestrates the invoice processing pipeline.
    
    Coordinates parser, analyzer, and mapper to transform PDFs into structured data.
    """
    
    def __init__(
        self,
        parser: PDFTextExtractor,
        analyzer: InvoiceAnalyzer,
        mapper: Optional[ProductMapper] = None
    ):
        """
        Initialize processor with dependencies.
        
        Args:
            parser: PDF text extractor
            analyzer: Invoice analyzer
            mapper: Product mapper (optional)
        """
        self.parser = parser
        self.analyzer = analyzer
        self.mapper = mapper
        
        logger.info("Initialized InvoiceProcessor")
        logger.info(f"  Parser: {type(parser).__name__}")
        logger.info(f"  Analyzer: {type(analyzer).__name__}")
        logger.info(f"  Mapper: {type(mapper).__name__ if mapper else 'None'}")
    
    def process(self, pdf_path: str, context: Optional[Dict] = None) -> Dict:
        """
        Process invoice from PDF to structured data.
        
        Args:
            pdf_path: Path to PDF file
            context: Optional context hints for analyzer
            
        Returns:
            Structured invoice data with items and metadata
            
        Raises:
            PDFExtractionError: If PDF cannot be read (permanent)
            ServiceUnavailableError: If LLM is down (temporary)
            PermanentError: For other permanent failures
            TemporaryError: For other temporary failures
        """
        logger.info(f"Processing invoice: {Path(pdf_path).name}")
        
        # Step 1: Extract text from PDF
        logger.info("Step 1: Extracting text from PDF")
        raw_text = self.parser.extract_text(pdf_path)
        logger.info(f"✓ Extracted {len(raw_text)} characters")
        
        # Step 2: Analyze with LLM
        logger.info("Step 2: Analyzing invoice with LLM")
        invoice_data = self.analyzer.analyze(raw_text, context)
        logger.info(f"✓ Extracted {len(invoice_data.get('items', []))} items")
        
        # Add metadata
        if '_metadata' not in invoice_data:
            invoice_data['_metadata'] = {}
        
        invoice_data['_metadata']['raw_text_length'] = len(raw_text)
        invoice_data['_metadata']['source_file'] = Path(pdf_path).name
        
        # Step 3: Map products to catalog (if mapper available)
        if self.mapper and invoice_data.get('items'):
            logger.info("Step 3: Mapping products to catalog")
            
            try:
                # Use mapper settings or defaults
                use_ml = getattr(self.mapper, 'use_ml', True)
                ml_threshold = getattr(self.mapper, 'ml_threshold', 0.4)
                
                mapped_items = self.mapper.map_invoice_items(
                    invoice_data['items'],
                    use_ml=use_ml,
                    ml_threshold=ml_threshold
                )
                invoice_data['items'] = mapped_items
                
                # Add mapping stats to metadata
                total = len(mapped_items)
                mapped = sum(1 for item in mapped_items if item.get('catalog_product_name'))
                invoice_data['_metadata']['mapping_rate'] = f"{mapped}/{total} ({mapped/total*100:.1f}%)"
                
                logger.info(f"✓ Mapped {mapped}/{total} items")
            
            except Exception as e:
                # Mapping failure is not critical
                logger.error(f"Product mapping failed: {e}")
                logger.info("Continuing with unmapped products")
        
        elif not self.mapper:
            logger.debug("No mapper configured, skipping product mapping")
        
        logger.info(f"✓ Processing complete")
        return invoice_data
