from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import logging
import pypdf
from pypdf.errors import PdfReadError

from exceptions import (
    PDFExtractionError,
    CorruptedPDFError,
    EmptyPDFError,
    EncryptedPDFError
)

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
    Extract text from PDF files with robust error handling.
    Forgiving approach: tries to read even with suspicious headers.
    """
    
    def __init__(self):
        """Initialize the PDF text extractor."""
        logger.info("Initialized PDFTextExtractor")
    
    def _validate_pdf_file(self, pdf_path: str) -> bool:
        """
        Validate basic file properties.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            True if file exists and not empty
            
        Raises:
            EmptyPDFError: If file doesn't exist or is empty
        """
        path = Path(pdf_path)
        
        # Check file exists
        if not path.exists():
            raise EmptyPDFError(f"File not found: {pdf_path}")
        
        # Check file size
        file_size = path.stat().st_size
        if file_size == 0:
            raise EmptyPDFError(f"File is empty (0 bytes)")
        
        if file_size < 100:
            logger.warning(f"File is very small ({file_size} bytes): {pdf_path}")
        
        # Check PDF header (non-blocking - just a warning)
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(10)
                if not header.startswith(b'%PDF-'):
                    logger.warning(f"Suspicious PDF header: {header[:10]}")
                    logger.warning(f"Expected '%PDF-' but will try to read anyway")
                else:
                    # Log version for debugging
                    try:
                        version = header[5:8].decode('ascii', errors='ignore')
                        logger.debug(f"PDF version: {version}")
                    except:
                        pass
        except Exception as e:
            logger.warning(f"Could not read header: {e}, will try to process anyway")
        
        return True
    
    def extract_text(self, file_path: str) -> str:
        """
        Extract text from PDF with comprehensive error handling.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            Extracted text content
            
        Raises:
            EmptyPDFError: File not found, empty, or no extractable text
            CorruptedPDFError: PDF structure is corrupted
            EncryptedPDFError: PDF is encrypted and cannot be decrypted
        """
        logger.info(f"Extracting text from: {file_path}")
        
        # Validate file (may raise EmptyPDFError)
        self._validate_pdf_file(file_path)
        
        try:
            # Try to open and extract text
            with open(file_path, 'rb') as file:
                try:
                    pdf_reader = pypdf.PdfReader(file, strict=False)
                    
                    # Check if PDF is encrypted
                    if pdf_reader.is_encrypted:
                        logger.warning(f"PDF is encrypted, attempting to decrypt")
                        try:
                            # Try empty password
                            if not pdf_reader.decrypt(''):
                                raise EncryptedPDFError("PDF is password-protected")
                        except Exception as e:
                            raise EncryptedPDFError(f"Cannot decrypt PDF: {e}")
                    
                    # Get number of pages
                    num_pages = len(pdf_reader.pages)
                    logger.debug(f"PDF has {num_pages} pages")
                    
                    if num_pages == 0:
                        raise EmptyPDFError("PDF has 0 pages")
                    
                    # Extract text from all pages
                    text_parts = []
                    failed_pages = 0
                    
                    for page_num in range(num_pages):
                        try:
                            page = pdf_reader.pages[page_num]
                            text = page.extract_text()
                            if text and text.strip():
                                text_parts.append(text)
                            else:
                                logger.debug(f"Page {page_num + 1} contains no text")
                        except Exception as e:
                            logger.warning(f"Error extracting text from page {page_num + 1}: {e}")
                            failed_pages += 1
                            continue
                    
                    if failed_pages > 0:
                        logger.warning(f"Failed to extract from {failed_pages}/{num_pages} pages")
                    
                    # Combine all text
                    full_text = "\n".join(text_parts)
                    
                    if not full_text or len(full_text.strip()) < 10:
                        raise EmptyPDFError(f"No text content extracted (got {len(full_text)} chars)")
                    
                    logger.info(f"Successfully extracted {len(full_text)} characters from {num_pages} pages")
                    return full_text
                
                except (EmptyPDFError, EncryptedPDFError):
                    # Re-raise our custom exceptions
                    raise
                
                except PdfReadError as e:
                    # pypdf specific errors - convert to our exception types
                    error_msg = str(e).lower()
                    
                    if 'invalid pdf header' in error_msg:
                        raise CorruptedPDFError("Invalid PDF structure")
                    elif 'startxref' in error_msg:
                        raise CorruptedPDFError("Corrupted xref table")
                    elif 'eof marker' in error_msg:
                        raise CorruptedPDFError("Truncated PDF (missing EOF)")
                    else:
                        raise CorruptedPDFError(f"PDF read error: {e}")
                
                except Exception as e:
                    # Unexpected errors
                    if 'decrypt' in str(e).lower() or 'encrypt' in str(e).lower():
                        raise EncryptedPDFError(f"Encryption error: {e}")
                    else:
                        raise CorruptedPDFError(f"Cannot read PDF: {e}")
        
        except (EmptyPDFError, CorruptedPDFError, EncryptedPDFError):
            # Re-raise our custom exceptions as-is
            raise
        
        except Exception as e:
            # Unexpected file access errors
            raise CorruptedPDFError(f"Cannot access file: {e}")
