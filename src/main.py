"""
Main entry point - ties everything together with proper dependency injection.
"""
import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict

from logger_config import setup_logger
from parser import PDFTextExtractor
from analyzer import InvoiceAnalyzer
from processor import InvoiceProcessor
from mapper import ProductMapper
from product_catalog import ProductCatalog
from database import InvoiceDatabase, SchemaManager, DatabaseProductCatalog
from email_monitor import EmailMonitor
from storage import save_invoice_json
from exceptions import (
    PermanentError,
    TemporaryError,
    is_permanent_error,
    is_temporary_error
)

logger = logging.getLogger("invoice_processor.main")


def get_config() -> Dict:
    """Read configuration from environment variables."""
    return {
        # LLM Configuration
        'llm_url': os.getenv('INVOICELYZER_LLM_URL', 'http://localhost:11434'),
        'llm_model': os.getenv('INVOICELYZER_LLM_MODEL', 'qwen2.5:14b'),
        'prompt_template': os.getenv('INVOICELYZER_PROMPT_TEMPLATE'),
        
        # Output Configuration
        'output_dir': os.getenv('INVOICELYZER_OUTPUT_DIR', './processed_invoices'),
        'save_json': os.getenv('INVOICELYZER_SAVE_JSON', 'true').lower() == 'true',
        
        # Database Configuration
        'database_url': os.getenv('INVOICELYZER_DATABASE_URL'),
        
        # Product Mapping Configuration
        'enable_mapping': os.getenv('INVOICELYZER_ENABLE_MAPPING', 'true').lower() == 'true',
        'mapping_use_ml': os.getenv('INVOICELYZER_MAPPING_USE_ML', 'true').lower() == 'true',
        'mapping_ml_threshold': float(os.getenv('INVOICELYZER_MAPPING_ML_THRESHOLD', '0.4')),
        
        # Logging Configuration
        'log_level': os.getenv('INVOICELYZER_LOG_LEVEL', 'INFO'),
        
        # Email Configuration
        'email_enabled': os.getenv('INVOICELYZER_EMAIL_ENABLED', 'false').lower() == 'true',
        'email_imap_server': os.getenv('INVOICELYZER_EMAIL_IMAP_SERVER'),
        'email_address': os.getenv('INVOICELYZER_EMAIL_ADDRESS'),
        'email_password': os.getenv('INVOICELYZER_EMAIL_PASSWORD'),
        'email_check_interval': int(os.getenv('INVOICELYZER_EMAIL_CHECK_INTERVAL', '300')),
        'email_mark_read': os.getenv('INVOICELYZER_EMAIL_MARK_READ', 'true').lower() == 'true',
        'email_continuous': os.getenv('INVOICELYZER_EMAIL_CONTINUOUS', 'true').lower() == 'true',
        'pdf_storage_dir': os.getenv('INVOICELYZER_PDF_STORAGE_DIR', './invoices')
    }


def create_invoice_processor(config: Dict) -> InvoiceProcessor:
    """
    Create InvoiceProcessor with all dependencies.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configured InvoiceProcessor instance
    """
    logger.info("Creating invoice processor...")
    
    # Create parser
    parser = PDFTextExtractor()
    
    # Create analyzer
    analyzer = InvoiceAnalyzer(
        llm_url=config['llm_url'],
        model=config['llm_model'],
        prompt_template=config.get('prompt_template')
    )
    
    # Create mapper (optional)
    mapper = None
    if config['enable_mapping'] and config['database_url']:
        try:
            # Create product catalog (database-backed)
            catalog = DatabaseProductCatalog(config['database_url'])
            
            # Create mapper with catalog and ML settings
            mapper = ProductMapper(
                catalog=catalog,
                use_ml=config['mapping_use_ml'],
                ml_threshold=config['mapping_ml_threshold']
            )
            
            logger.info("✓ Product mapper enabled")
        except Exception as e:
            logger.warning(f"Failed to create product mapper: {e}")
            logger.info("Continuing without product mapping")
    
    # Create processor
    processor = InvoiceProcessor(
        parser=parser,
        analyzer=analyzer,
        mapper=mapper
    )
    
    logger.info("✓ Invoice processor created")
    return processor


def init_database(config: Dict) -> Optional[InvoiceDatabase]:
    """
    Initialize database connection and schema.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        InvoiceDatabase instance or None
    """
    if not config.get('database_url'):
        logger.info("No database configured")
        return None
    
    try:
        logger.info("Initializing database...")
        
        # Create schema if needed
        schema_manager = SchemaManager(config['database_url'])
        schema_manager.create_schema()
        logger.info("✓ Database schema verified")
        
        # Create database instance
        db = InvoiceDatabase(config['database_url'])
        logger.info("✓ Database initialized")
        
        return db
    
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        logger.warning("Continuing without database")
        return None


def process_invoice_file(
    pdf_path: str,
    processor: InvoiceProcessor,
    database: Optional[InvoiceDatabase],
    config: Dict,
    sender: Optional[str] = None
) -> Optional[Dict]:
    """
    Process a single invoice file.
    
    This is the callback function for email monitoring and batch processing.
    
    Args:
        pdf_path: Path to PDF file
        processor: InvoiceProcessor instance
        database: Database instance (optional)
        config: Configuration dictionary
        sender: Email sender (optional)
        
    Returns:
        Invoice data on success, None on permanent failure
        
    Raises:
        TemporaryError: On temporary failures (should retry)
    """
    try:
        logger.info(f"Processing: {Path(pdf_path).name}")
        
        # Process invoice
        try:
            invoice_data = processor.process(pdf_path)
        
        except PermanentError as e:
            logger.error(f"❌ Permanent failure: {type(e).__name__}: {e}")
            logger.warning("This will not succeed on retry")
            return None
        
        except TemporaryError as e:
            logger.warning(f"⚠️ Temporary failure: {type(e).__name__}: {e}")
            logger.info("This might succeed later - will retry")
            raise  # Re-raise for caller to handle
        
        # Add sender to metadata if provided
        if sender:
            invoice_data['_metadata']['email_sender'] = sender
        
        # Save to database (best effort)
        if database:
            try:
                invoice_id = database.save_invoice(invoice_data)
                logger.info(f"✓ Saved to database (ID: {invoice_id})")
            except Exception as e:
                logger.error(f"Database save failed: {e}")
                logger.warning("Continuing without database save")
        
        # Save to JSON (best effort)
        if config['save_json']:
            try:
                json_file = save_invoice_json(
                    invoice_data,
                    config['output_dir'],
                    pdf_path
                )
                logger.info(f"✓ Saved JSON: {Path(json_file).name}")
            except Exception as e:
                logger.error(f"JSON save failed: {e}")
        
        logger.info(f"✓ Successfully processed invoice")
        return invoice_data
    
    except TemporaryError:
        # Re-raise temporary errors
        raise
    
    except Exception as e:
        # Unknown error - classify it
        if is_permanent_error(e):
            logger.error(f"❌ Permanent error: {e}")
            return None
        elif is_temporary_error(e):
            logger.warning(f"⚠️ Temporary error: {e}")
            raise TemporaryError(f"Temporary failure: {e}")
        else:
            # Unknown - treat as permanent
            logger.error(f"❌ Unknown error (treating as permanent): {e}", exc_info=True)
            return None


def create_email_callback(
    processor: InvoiceProcessor,
    database: Optional[InvoiceDatabase],
    config: Dict
):
    """
    Create callback function for email monitoring.
    
    Args:
        processor: InvoiceProcessor instance
        database: Database instance
        config: Configuration dictionary
        
    Returns:
        Callback function(pdf_path, sender) -> bool
    """
    def callback(pdf_path: str, sender: str) -> bool:
        """
        Process PDF from email.
        
        Returns:
            True = mark email as read
            False = keep email unread (retry later)
        """
        try:
            result = process_invoice_file(pdf_path, processor, database, config, sender)
            
            if result is None:
                # Permanent failure - mark as read
                logger.info("✓ Permanent failure - marking email as read")
                return True
            
            # Success - mark as read
            logger.info("✓ Success - marking email as read")
            return True
        
        except TemporaryError as e:
            # Temporary failure - keep unread
            logger.info("⏳ Temporary failure - keeping email unread")
            return False
        
        except Exception as e:
            # Unknown error - mark as read to avoid loops
            logger.error(f"❌ Unexpected error: {e}")
            logger.info("✓ Marking email as read to avoid retry loop")
            return True
    
    return callback


def run_email_monitor(config: Dict):
    """
    Run email monitoring mode.
    
    Args:
        config: Configuration dictionary
    """
    logger.info("="*60)
    logger.info("EMAIL MONITORING MODE")
    logger.info("="*60)
    
    # Validate email configuration
    if not all([config.get('email_imap_server'),
                config.get('email_address'),
                config.get('email_password')]):
        logger.error("Missing email configuration")
        logger.error("Required: INVOICELYZER_EMAIL_IMAP_SERVER, INVOICELYZER_EMAIL_ADDRESS, INVOICELYZER_EMAIL_PASSWORD")
        return 1
    
    # Initialize components
    processor = create_invoice_processor(config)
    database = init_database(config)
    
    # Create email monitor
    email_monitor = EmailMonitor(
        imap_server=config['email_imap_server'],
        email=config['email_address'],
        password=config['email_password'],
        pdf_storage_dir=config['pdf_storage_dir']
    )
    
    # Create callback
    callback = create_email_callback(processor, database, config)
    
    # Start monitoring
    if config['email_continuous']:
        logger.info("Starting continuous monitoring...")
        email_monitor.monitor_continuous(
            process_callback=callback,
            check_interval=config['email_check_interval'],
            mark_as_read=config['email_mark_read']
        )
    else:
        logger.info("Performing single check...")
        count = email_monitor.check_new_emails(
            process_callback=callback,
            mark_as_read=config['email_mark_read']
        )
        logger.info(f"✓ Processed {count} emails")
    
    return 0


def run_batch_processing(pdf_files: list, config: Dict):
    """
    Run batch processing mode.
    
    Args:
        pdf_files: List of PDF file paths
        config: Configuration dictionary
    """
    logger.info("="*60)
    logger.info("BATCH PROCESSING MODE")
    logger.info("="*60)
    logger.info(f"Files to process: {len(pdf_files)}")
    logger.info("")
    
    # Initialize components
    processor = create_invoice_processor(config)
    database = init_database(config)
    
    # Process each file
    stats = {'success': 0, 'permanent': 0, 'temporary': 0}
    
    for i, pdf_file in enumerate(pdf_files, 1):
        logger.info(f"[{i}/{len(pdf_files)}] {Path(pdf_file).name}")
        logger.info("="*60)
        
        try:
            result = process_invoice_file(pdf_file, processor, database, config)
            
            if result:
                logger.info(f"✓ SUCCESS")
                stats['success'] += 1
            else:
                logger.warning(f"✗ FAILED (permanent)")
                stats['permanent'] += 1
        
        except TemporaryError as e:
            logger.warning(f"⏳ TEMPORARY FAILURE")
            logger.info(f"Error: {e}")
            stats['temporary'] += 1
        
        except Exception as e:
            logger.error(f"❌ ERROR: {e}")
            stats['permanent'] += 1
        
        logger.info("")
    
    # Summary
    logger.info("="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    logger.info(f"Total files:       {len(pdf_files)}")
    logger.info(f"✓ Successful:      {stats['success']}")
    logger.info(f"✗ Permanent fails: {stats['permanent']}")
    logger.info(f"⏳ Temporary fails: {stats['temporary']}")
    logger.info("="*60)
    
    return 0


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Invoice Processor')
    parser.add_argument('files', nargs='*', help='PDF files to process')
    parser.add_argument('--email', action='store_true', help='Run in email monitoring mode')
    
    args = parser.parse_args()
    
    # Load configuration
    config = get_config()
    
    # Setup logging
    global logger
    logger = setup_logger(level=config['log_level'])
    
    logger.info("Invoicelyzer - Invoice Processing System")
    logger.info("")
    
    try:
        if args.email or config['email_enabled']:
            # Email monitoring mode
            return run_email_monitor(config)
        
        elif args.files:
            # Batch processing mode
            return run_batch_processing(args.files, config)
        
        else:
            logger.error("No files specified and email mode not enabled")
            logger.info("Usage:")
            logger.info("  python main.py file1.pdf file2.pdf ...")
            logger.info("  python main.py --email")
            return 1
    
    except KeyboardInterrupt:
        logger.info("\nStopped by user")
        return 0
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

