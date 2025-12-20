import logging
import json
import re
from typing import Optional
from pathlib import Path

from email_monitor import EmailMonitor
from processor import InvoiceProcessor
from database import InvoiceDatabase

logger = logging.getLogger("invoice_processor.email_processor")


def sanitize_filename(text: str) -> str:
    """
    Sanitize text for use in filename.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text safe for filenames
    """
    # Replace problematic characters
    text = text.replace('/', '-')
    text = text.replace('\\', '-')
    text = text.replace(':', '-')
    text = text.replace('*', '-')
    text = text.replace('?', '-')
    text = text.replace('"', '-')
    text = text.replace('<', '-')
    text = text.replace('>', '-')
    text = text.replace('|', '-')
    text = text.replace(' ', '_')
    
    # Remove any other non-alphanumeric characters except - and _
    text = re.sub(r'[^\w\-]', '', text)
    
    return text


def save_invoice_json(invoice_data: dict, output_dir: str) -> str:
    """
    Save processed invoice to JSON file.
    
    Args:
        invoice_data: Structured invoice data
        output_dir: Directory to save output
        
    Returns:
        Path to saved file
    """
    # Create output directory if needed
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Output directory: {output_path}")
    
    # Generate filename from invoice data with sanitization
    store = sanitize_filename(invoice_data.get('store', 'unknown').lower())
    date = invoice_data.get('date', 'nodate').replace('-', '')
    
    # Sanitize invoice number (handles "/" and other special chars)
    invoice_num = invoice_data.get('invoice_number')
    if invoice_num and invoice_num != 'null':
        invoice_num = sanitize_filename(str(invoice_num))
    else:
        invoice_num = 'noinv'
    
    filename = f"{store}_{date}_{invoice_num}.json"
    filepath = output_path / filename
    
    logger.debug(f"Saving invoice to: {filepath}")
    logger.debug(f"Filename components - store: {store}, date: {date}, invoice_num: {invoice_num}")
    
    # Save JSON
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(invoice_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Invoice saved to: {filepath}")
    return str(filepath)


class EmailInvoiceProcessor:
    """
    Coordinates email monitoring and invoice processing.
    """
    
    def __init__(
        self,
        email_monitor: EmailMonitor,
        invoice_processor: InvoiceProcessor,
        database: Optional[InvoiceDatabase] = None,
        save_json: bool = True,
        output_dir: str = "./processed_invoices"
    ):
        """
        Args:
            email_monitor: Email monitoring instance
            invoice_processor: Invoice processing instance
            database: Database instance (optional)
            save_json: Whether to save JSON files
            output_dir: Directory for JSON output
        """
        self.email_monitor = email_monitor
        self.invoice_processor = invoice_processor
        self.database = database
        self.save_json = save_json
        self.output_dir = Path(output_dir)
        
        if self.save_json:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
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
            
            # Process the invoice
            invoice_data = self.invoice_processor.process(pdf_path)
            
            # Add sender to metadata
            if '_metadata' not in invoice_data:
                invoice_data['_metadata'] = {}
            invoice_data['_metadata']['email_sender'] = sender
            
            # Save to database
            if self.database:
                try:
                    invoice_id = self.database.save_invoice(invoice_data)
                    logger.info(f"✓ Saved to database with ID: {invoice_id}")
                except Exception as e:
                    logger.error(f"Failed to save to database: {str(e)}")
                    return False
            
            # Save to JSON
            if self.save_json:
                save_invoice_json(invoice_data, str(self.output_dir))
            
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
    ):
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
            