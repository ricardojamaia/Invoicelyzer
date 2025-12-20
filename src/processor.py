from pathlib import Path
from typing import Dict, Optional
import json
import logging

from parser import InvoiceExtractor, PDFTextExtractor
from analyzer import InvoiceAnalyzer

logger = logging.getLogger("invoice_processor.processor")


class InvoiceProcessor:
    """
    Main processor that coordinates extraction and analysis.
    """
    
    def __init__(
        self, 
        llm_url: str,
        model: str = "llama3.2:3b",
        extractor: Optional[InvoiceExtractor] = None,
        prompt_template: Optional[str] = None
    ):
        """
        Args:
            llm_url: URL of LLM API endpoint
            model: LLM model name
            extractor: Text extraction strategy (defaults to PDFTextExtractor)
            prompt_template: Path to custom prompt template file (optional)
        """
        self.extractor = extractor or PDFTextExtractor()
        self.analyzer = InvoiceAnalyzer(
            llm_url=llm_url, 
            model=model,
            prompt_template=prompt_template
        )
        
        logger.info(f"Initialized InvoiceProcessor with extractor: {self.extractor.__class__.__name__}")
    
    def process(self, file_path: str, context: Optional[Dict] = None) -> Dict:
        """
        Complete pipeline: extract and analyze invoice.
        
        Args:
            file_path: Path to invoice file
            context: Optional context for analysis
            
        Returns:
            Structured invoice data with metadata
        """
        logger.info(f"Starting invoice processing: {file_path}")
        
        # Step 1: Extract raw text
        logger.info("Step 1/2: Extracting text from file")
        raw_text = self.extractor.extract_text(file_path)
        
        if not raw_text:
            logger.error("No text extracted from file")
            raise Exception("No text extracted from file")
        
        logger.info(f"Extracted {len(raw_text)} characters from file")
        
        # Step 2: Analyze with LLM
        logger.info("Step 2/2: Analyzing invoice with LLM")
        invoice_data = self.analyzer.analyze(raw_text, context)
        
        # Add metadata
        invoice_data['_metadata'] = {
            'source_file': str(Path(file_path).name),
            'raw_text_length': len(raw_text),
            'extractor': self.extractor.__class__.__name__,
            'analyzer': self.analyzer.__class__.__name__
        }
        
        logger.info(
            f"Processing complete - Store: {invoice_data.get('store', 'Unknown')}, "
            f"Items: {len(invoice_data.get('items', []))}, "
            f"Total: €{invoice_data.get('total', 0)}"
        )
        
        return invoice_data