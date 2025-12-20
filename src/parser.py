from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict
import logging

logger = logging.getLogger("invoice_processor.parser")


class InvoiceExtractor(ABC):
    """
    Abstract base class for invoice text extraction.
    Allows different extraction strategies (PDF, OCR, etc.)
    """
    
    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        """
        Extract raw text from invoice file.
        
        Args:
            file_path: Path to the invoice file
            
        Returns:
            Raw text content
        """
        pass


class PDFTextExtractor(InvoiceExtractor):
    """
    Extract text from text-based PDF files.
    """
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from PDF using pypdf.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text content
        """
        import pypdf
        
        logger.debug(f"Starting PDF text extraction from: {file_path}")
        
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = pypdf.PdfReader(file)
                num_pages = len(pdf_reader.pages)
                logger.debug(f"PDF has {num_pages} pages")
                
                text = ""
                for i, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    text += page_text + "\n"
                    logger.debug(f"Extracted {len(page_text)} chars from page {i+1}")
                
                if not text.strip():
                    logger.warning("No text extracted from PDF - might be scanned/image-based")
                    raise ValueError("No text extracted from PDF - might be scanned/image-based")
                
                logger.info(f"Successfully extracted {len(text)} characters from PDF")
                logger.debug("Invoice:\n" + "-"*30 + "\n" + text + "-"*30)
                return text.strip()
                
        except Exception as e:
            logger.error(f"Error extracting PDF text: {str(e)}", exc_info=True)
            raise Exception(f"Error extracting PDF text: {str(e)}")