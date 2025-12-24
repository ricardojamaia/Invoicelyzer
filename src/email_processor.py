"""
Email processor using exception hierarchy for smart email marking.
"""
import logging
from typing import Optional, Callable
from pathlib import Path

from email_monitor import EmailMonitor
from processor import InvoiceProcessor
from database import InvoiceDatabase
from exceptions import (
    PermanentError,
    TemporaryError,
    is_permanent_error,
    is_temporary_error
)

logger = logging.getLogger("invoice_processor.email_processor")


class EmailInvoiceProcessor:
    """
    Coordinates email monitoring and invoice processing.
    
    Uses exception types to intelligently decide when to mark emails as read:
    - PermanentError → Mark as read (won't succeed on retry)
    - TemporaryError → Keep unread (will retry later)
    """
    
    def __init__(
        self,
        email_monitor: EmailMonitor,
        invoice_processor: InvoiceProcessor,
        database: Optional[InvoiceDatabase] = None,
        process_callback: Optional[Callable] = None
    ):
        """
        Args:
            email_monitor: Email monitoring instance
            invoice_processor: Invoice processing instance
            database: Database instance (optional)
            process_callback: Function(pdf_path, sender) -> invoice_data to process PDFs
        """
        self.email_monitor = email_monitor
        self.invoice_processor = invoice_processor
        self.database = database
        self.process_callback = process_callback
        
        logger.info("Initialized EmailInvoiceProcessor")
    
    def process_pdf(self, pdf_path: str, sender: str) -> bool:
        """
        Process a single PDF invoice from email.
        
        Decision logic based on exception types:
        - PermanentError → Mark as read (won't retry)
        - TemporaryError → Keep unread (will retry)
        - Success → Mark as read
        - Unknown error → Mark as read (safe default)
        
        Args:
            pdf_path: Path to PDF file
            sender: Email sender address
            
        Returns:
            True = mark email as read
            False = keep unread (will retry later)
        """
        try:
            logger.info(f"📧 Processing PDF from {sender}: {Path(pdf_path).name}")
            
            # Use callback if provided (from main.py)
            if self.process_callback:
                try:
                    result = self.process_callback(pdf_path, sender)
                    
                    if result is None:
                        # None = permanent failure
                        logger.warning("Processing returned None (permanent failure)")
                        logger.info("✓ Marking email as read")
                        return True
                    
                    # Success
                    logger.info("✓ Processing successful")
                    logger.info("✓ Marking email as read")
                    return True
                
                except TemporaryError as e:
                    # Temporary failure - keep unread
                    logger.warning(f"⚠️ Temporary error: {e}")
                    logger.info("⏳ Keeping email unread (will retry)")
                    return False
                
                except PermanentError as e:
                    # Permanent failure - mark as read
                    logger.error(f"❌ Permanent error: {e}")
                    logger.info("✓ Marking email as read (won't retry)")
                    return True
                
                except Exception as e:
                    # Unknown error - check type
                    if is_temporary_error(e):
                        logger.warning(f"⚠️ Temporary error: {e}")
                        logger.info("⏳ Keeping email unread")
                        return False
                    else:
                        # Treat as permanent
                        logger.error(f"❌ Error (treating as permanent): {e}")
                        logger.info("✓ Marking email as read")
                        return True
            
            # No callback - use direct processing
            invoice_data = self.invoice_processor.process(pdf_path)
            
            # Add sender to metadata
            if '_metadata' not in invoice_data:
                invoice_data['_metadata'] = {}
            invoice_data['_metadata']['email_sender'] = sender
            invoice_data['_metadata']['source_file'] = Path(pdf_path).name
            
            # Save to database (best effort)
            if self.database:
                try:
                    invoice_id = self.database.save_invoice(invoice_data)
                    logger.info(f"✓ Saved to database with ID: {invoice_id}")
                except Exception as e:
                    logger.error(f"Database save failed: {e}")
                    # Continue - we have the PDF saved
            
            logger.info(f"✓ Successfully processed invoice")
            logger.info("✓ Marking email as read")
            return True
        
        except TemporaryError as e:
            # Temporary failure - keep unread for retry
            logger.warning(f"⚠️ Temporary error: {type(e).__name__}: {e}")
            logger.info("⏳ Keeping email unread (will retry)")
            return False
        
        except PermanentError as e:
            # Permanent failure - mark as read
            logger.error(f"❌ Permanent error: {type(e).__name__}: {e}")
            logger.info("✓ Marking email as read (won't retry)")
            return True
        
        except Exception as e:
            # Unknown error - check if we can classify it
            if is_temporary_error(e):
                logger.warning(f"⚠️ Temporary error: {e}")
                logger.info("⏳ Keeping email unread")
                return False
            elif is_permanent_error(e):
                logger.error(f"❌ Permanent error: {e}")
                logger.info("✓ Marking email as read")
                return True
            else:
                # Unknown type - mark as read (safe default to avoid loops)
                logger.error(f"❌ Unknown error: {e}", exc_info=True)
                logger.warning("Treating as permanent to avoid infinite retries")
                logger.info("✓ Marking email as read")
                return True
    
    def start_monitoring(
        self,
        check_interval: int = 300,
        mark_as_read: bool = True,
        continuous: bool = True
    ) -> None:
        """
        Start monitoring emails for invoices.
        
        Args:
            check_interval: Seconds between checks
            mark_as_read: Mark processed emails as read
            continuous: Run continuously or check once
        """
        if continuous:
            logger.info("🚀 Starting continuous email monitoring")
            logger.info(f"   Check interval: {check_interval}s")
            logger.info(f"   Mark as read: {mark_as_read}")
            logger.info("")
            
            self.email_monitor.monitor_continuous(
                process_callback=self.process_pdf,
                check_interval=check_interval,
                mark_as_read=mark_as_read
            )
        else:
            logger.info("📧 Performing single email check")
            count = self.email_monitor.check_new_invoices(
                process_callback=self.process_pdf,
                mark_as_read=mark_as_read
            )
            logger.info(f"✓ Check complete: {count} invoices processed")
