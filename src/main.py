#!/usr/bin/env python3
"""
Invoice Processor - Main entry point
Processes Portuguese supermarket invoices from PDF files.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List

from logger_config import setup_logger
from processor import InvoiceProcessor
from database import InvoiceDatabase
from email_monitor import EmailMonitor
from email_processor import EmailInvoiceProcessor, save_invoice_json


def load_sender_config(config_path: str) -> Dict[str, List[str]]:
    """
    Load sender configuration from JSON file.
    
    Args:
        config_path: Path to sender configuration JSON file
        
    Returns:
        Dictionary mapping folder names to sender email lists
    """
    logger = logging.getLogger("invoice_processor.main")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            sender_config = json.load(f)
        
        # Validate format
        if not isinstance(sender_config, dict):
            raise ValueError("Sender config must be a JSON object")
        
        for folder_name, emails in sender_config.items():
            if not isinstance(emails, list):
                raise ValueError(f"Sender list for '{folder_name}' must be an array")
            if not all(isinstance(e, str) for e in emails):
                raise ValueError(f"All senders for '{folder_name}' must be strings")
        
        total_senders = sum(len(emails) for emails in sender_config.values())
        logger.info(f"Loaded sender config: {len(sender_config)} folders, {total_senders} total senders")
        
        return sender_config
        
    except FileNotFoundError:
        logger.error(f"Sender config file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in sender config: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading sender config: {e}")
        raise


def get_config() -> dict:
    """
    Read configuration from environment variables.
    
    Returns:
        Configuration dictionary
    """
    return {
        'llm_url': os.getenv('INVOICELYZER_LLM_URL', 'http://localhost:11434'),
        'llm_model': os.getenv('INVOICELYZER_LLM_MODEL', 'llama3.2:3b'),
        'output_dir': os.getenv('INVOICELYZER_OUTPUT_DIR', './processed_invoices'),
        'log_level': os.getenv('INVOICELYZER_LOG_LEVEL', 'INFO'),
        'prompt_template': os.getenv('INVOICELYZER_PROMPT_TEMPLATE'),
        'database_url': os.getenv('INVOICELYZER_DATABASE_URL'),
        'save_json': os.getenv('INVOICELYZER_SAVE_JSON', 'true').lower() == 'true',
        # Email settings
        'email_enabled': os.getenv('INVOICELYZER_EMAIL_ENABLED', 'false').lower() == 'true',
        'email_imap_server': os.getenv('INVOICELYZER_EMAIL_IMAP_SERVER'),
        'email_address': os.getenv('INVOICELYZER_EMAIL_ADDRESS'),
        'email_password': os.getenv('INVOICELYZER_EMAIL_PASSWORD'),
        'email_sender_config': os.getenv('INVOICELYZER_EMAIL_SENDER_CONFIG', './config/senders.json'),
        'email_check_interval': int(os.getenv('INVOICELYZER_EMAIL_CHECK_INTERVAL', '300')),
        'email_mark_read': os.getenv('INVOICELYZER_EMAIL_MARK_READ', 'true').lower() == 'true',
        'email_continuous': os.getenv('INVOICELYZER_EMAIL_CONTINUOUS', 'true').lower() == 'true',
        'pdf_storage_dir': os.getenv('INVOICELYZER_PDF_STORAGE_DIR', './invoices')
    }


def process_invoice_file(
    pdf_path: str, 
    config: dict, 
    logger: logging.Logger,
    db: Optional[InvoiceDatabase] = None
) -> Optional[dict]:
    """
    Process a single invoice PDF file.
    
    Args:
        pdf_path: Path to PDF file
        config: Configuration dictionary
        logger: Logger instance
        db: Database instance (optional)
        
    Returns:
        Processed invoice data or None if error
    """
    try:
        logger.info(f"Processing file: {pdf_path}")
        
        # Initialize processor with config
        processor = InvoiceProcessor(
            llm_url=config['llm_url'],
            model=config['llm_model'],
            prompt_template=config.get('prompt_template')
        )
        
        # Process invoice
        invoice_data = processor.process(pdf_path)
        
        # Save to database if configured
        if db:
            try:
                invoice_id = db.save_invoice(invoice_data)
                logger.info(f"✓ Saved to database with ID: {invoice_id}")
            except Exception as e:
                logger.error(f"Failed to save to database: {str(e)}")
                # Continue even if database save fails
        
        # Save to JSON if configured
        if config['save_json']:
            json_file = save_invoice_json(invoice_data, config['output_dir'])
            logger.info(f"✓ Saved JSON to: {json_file}")
        
        logger.info(f"✓ Successfully processed invoice")
        
        return invoice_data
        
    except Exception as e:
        logger.error(f"✗ Failed to process {pdf_path}: {str(e)}", exc_info=True)
        return None


def init_database(config: dict, logger: logging.Logger) -> Optional[InvoiceDatabase]:
    """
    Initialize database connection and schema.
    
    Args:
        config: Configuration dictionary
        logger: Logger instance
        
    Returns:
        Database instance or None if not configured
    """
    if not config.get('database_url'):
        logger.info("No database configured, skipping database storage")
        return None
    
    try:
        db = InvoiceDatabase(config['database_url'])
        db.create_schema()
        logger.info("Database initialized successfully")
        return db
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        logger.warning("Continuing without database storage")
        return None


def run_email_monitor(config: dict, logger: logging.Logger, db: Optional[InvoiceDatabase]):
    """
    Run email monitoring mode.
    
    Args:
        config: Configuration dictionary
        logger: Logger instance
        db: Database instance
    """
    # Validate email configuration
    if not config['email_imap_server'] or not config['email_address'] or not config['email_password']:
        logger.error("Email monitoring requires: INVOICELYZER_EMAIL_IMAP_SERVER, INVOICELYZER_EMAIL_ADDRESS, INVOICELYZER_EMAIL_PASSWORD")
        sys.exit(1)
    
    # Load sender configuration
    try:
        sender_config = load_sender_config(config['email_sender_config'])
    except Exception as e:
        logger.error(f"Failed to load sender configuration: {e}")
        logger.info(f"Please create a sender config file at: {config['email_sender_config']}")
        logger.info("See config/senders.example.json for format")
        sys.exit(1)
    
    logger.info(f"PDF storage: {config['pdf_storage_dir']}")
    
    # Initialize email monitor
    email_monitor = EmailMonitor(
        imap_server=config['email_imap_server'],
        email=config['email_address'],
        password=config['email_password'],
        sender_config=sender_config,
        pdf_storage_dir=config['pdf_storage_dir']
    )
    
    # Initialize invoice processor
    invoice_processor = InvoiceProcessor(
        llm_url=config['llm_url'],
        model=config['llm_model'],
        prompt_template=config.get('prompt_template')
    )
    
    # Initialize email processor
    email_processor = EmailInvoiceProcessor(
        email_monitor=email_monitor,
        invoice_processor=invoice_processor,
        database=db,
        save_json=config['save_json'],
        output_dir=config['output_dir']
    )
    
    # Start monitoring
    email_processor.start_monitoring(
        check_interval=config['email_check_interval'],
        mark_as_read=config['email_mark_read'],
        continuous=config['email_continuous']
    )


def main():
    """Main entry point."""
    
    # Get configuration
    config = get_config()
    
    # Setup logging
    logger = setup_logger(level=config['log_level'])
    
    # Check if running in email monitoring mode
    if '--monitor-email' in sys.argv or config['email_enabled']:
        logger.info("="*60)
        logger.info("Invoice Processor - Email Monitor Mode")
        logger.info("="*60)
        logger.info(f"Email:        {config['email_address']}")
        logger.info(f"IMAP Server:  {config['email_imap_server']}")
        logger.info(f"Check every:  {config['email_check_interval']}s")
        logger.info(f"Continuous:   {config['email_continuous']}")
        logger.info(f"Database:     {'Configured' if config.get('database_url') else 'Not configured'}")
        logger.info("="*60)
        
        # Initialize database
        db = init_database(config, logger)
        
        # Run email monitor
        run_email_monitor(config, logger, db)
        return
    
    # Normal file processing mode
    if len(sys.argv) < 2:
        print("Usage: python main.py <invoice.pdf> [invoice2.pdf ...]")
        print("   or: python main.py --monitor-email")
        print("\nEnvironment variables:")
        print("  INVOICELYZER_LLM_URL              - LLM API URL (default: http://localhost:11434)")
        print("  INVOICELYZER_LLM_MODEL            - Model name (default: llama3.2:3b)")
        print("  INVOICELYZER_OUTPUT_DIR           - Output directory (default: ./processed_invoices)")
        print("  INVOICELYZER_LOG_LEVEL            - Logging level (default: INFO)")
        print("  INVOICELYZER_DATABASE_URL         - PostgreSQL connection string (optional)")
        print("  INVOICELYZER_SAVE_JSON            - Save JSON files (default: true)")
        print("  INVOICELYZER_PROMPT_TEMPLATE      - Custom prompt template path (optional)")
        print("\nEmail monitoring:")
        print("  INVOICELYZER_EMAIL_ENABLED        - Enable email monitoring (default: false)")
        print("  INVOICELYZER_EMAIL_IMAP_SERVER    - IMAP server (e.g., imap.gmail.com)")
        print("  INVOICELYZER_EMAIL_ADDRESS        - Email address")
        print("  INVOICELYZER_EMAIL_PASSWORD       - Email password or app password")
        print("  INVOICELYZER_EMAIL_SENDER_CONFIG  - Path to sender config JSON (default: ./config/senders.json)")
        print("  INVOICELYZER_EMAIL_CHECK_INTERVAL - Seconds between checks (default: 300)")
        print("  INVOICELYZER_EMAIL_MARK_READ      - Mark processed emails as read (default: true)")
        print("  INVOICELYZER_EMAIL_CONTINUOUS     - Run continuously (default: true)")
        print("  INVOICELYZER_PDF_STORAGE_DIR      - PDF storage directory (default: ./invoices)")
        sys.exit(1)
    
    logger.info("="*60)
    logger.info("Invoice Processor Started")
    logger.info("="*60)
    logger.info(f"LLM URL:      {config['llm_url']}")
    logger.info(f"Model:        {config['llm_model']}")
    logger.info(f"Output dir:   {config['output_dir']}")
    logger.info(f"Save JSON:    {config['save_json']}")
    logger.info(f"Database:     {'Configured' if config.get('database_url') else 'Not configured'}")
    logger.info(f"Log level:    {config['log_level']}")
    logger.info("="*60)
    
    # Initialize database
    db = init_database(config, logger)
    
    # Process each PDF file
    pdf_files = sys.argv[1:]
    results = []
    
    for pdf_path in pdf_files:
        if not Path(pdf_path).exists():
            logger.error(f"File not found: {pdf_path}")
            continue
        
        logger.info(f"Processing: {pdf_path}")
        logger.info("-"*60)
        
        result = process_invoice_file(pdf_path, config, logger, db)
        results.append({
            'file': pdf_path,
            'success': result is not None,
            'data': result
        })
    
    # Summary
    logger.info("="*60)
    logger.info("PROCESSING SUMMARY")
    logger.info("="*60)
    successful = sum(1 for r in results if r['success'])
    logger.info(f"Total files:  {len(results)}")
    logger.info(f"Successful:   {successful}")
    logger.info(f"Failed:       {len(results) - successful}")
    logger.info("="*60)
    

if __name__ == "__main__":
    main()

