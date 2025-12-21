"""
Coordinates email monitoring and invoice processing.
"""
import logging
from typing import Optional
from pathlib import Path

from email_monitor import EmailMonitor
from processor import InvoiceProcessor
from database import InvoiceDatabase

logger = logging.getLogger("invoice_processor.email_processor")


class EmailInvoiceProcessor:
    """
    Coordinates email monitoring and invoice processing.
    """
    
    def __init__(
        self,
        email_monitor: EmailMonitor,
        invoice_processor: InvoiceProcessor,
        database: Optional[InvoiceDatabase] = None,
        process_callback = None  # Function to process each PDF
    ):
        """
        Args:
            email_monitor: Email monitoring instance
            invoice_processor: Invoice processing instance
            database: Database instance (optional)
            process_callback: Function(pdf_path, sender) -> bool to process PDFs
        """
        self.email_monitor = email_monitor
        self.invoice_processor = invoice_processor
        self.database = database
        self.process_callback = process_callback
        
        logger.info("Initialized EmailInvoiceProcessor")
    
    def process_pdf(self, pdf_path: str, sender: str) -> bool:
        """
        Process a single PDF invoice.
        
        Args:
            pdf_path: Path to PDF file
            sender: Email sender address
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Processing PDF from {sender}: {pdf_path}")
            
            # Use provided callback if available
            if self.process_callback:
                return self.process_callback(pdf_path, sender)
            
            # Otherwise, basic processing
            invoice_data = self.invoice_processor.process(pdf_path)
            
            # Add sender to metadata
            if '_metadata' not in invoice_data:
                invoice_data['_metadata'] = {}
            invoice_data['_metadata']['email_sender'] = sender
            invoice_data['_metadata']['source_file'] = Path(pdf_path).name
            
            # Save to database
            if self.database:
                try:
                    invoice_id = self.database.save_invoice(invoice_data)
                    logger.info(f"✓ Saved to database with ID: {invoice_id}")
                except Exception as e:
                    logger.error(f"Failed to save to database: {str(e)}")
                    return False
            
            logger.info(f"✓ Successfully processed invoice from {sender}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to process PDF from {sender}: {str(e)}", exc_info=True)
            return False
    
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
            logger.info("Starting continuous email monitoring")
            self.email_monitor.monitor_continuous(
                process_callback=self.process_pdf,
                check_interval=check_interval,
                mark_as_read=mark_as_read
            )
        else:
            logger.info("Performing single email check")
            count = self.email_monitor.check_new_invoices(
                process_callback=self.process_pdf,
                mark_as_read=mark_as_read
            )
            logger.info(f"Check complete: {count} invoices processed")

            