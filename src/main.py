#!/usr/bin/env python3
"""
Invoice Processor - Main entry point
Processes Portuguese supermarket invoices from PDF files.
"""

import os
import sys
import json
import logging
import re
from pathlib import Path
from typing import Optional

from logger_config import setup_logger
from processor import InvoiceProcessor
from database import InvoiceDatabase


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
        'save_json': os.getenv('INVOICELYZER_SAVE_JSON', 'true').lower() == 'true'
    }


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


def save_invoice_json(invoice_data: dict, output_dir: str, logger: logging.Logger) -> str:
    """
    Save processed invoice to JSON file.
    
    Args:
        invoice_data: Structured invoice data
        output_dir: Directory to save output
        logger: Logger instance
        
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
            json_file = save_invoice_json(invoice_data, config['output_dir'], logger)
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


def main():
    """Main entry point."""
    
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python main.py <invoice.pdf> [invoice2.pdf ...]")
        print("\nEnvironment variables:")
        print("  INVOICELYZER_LLM_URL         - LLM API URL (default: http://localhost:11434)")
        print("  INVOICELYZER_LLM_MODEL       - Model name (default: llama3.2:3b)")
        print("  INVOICELYZER_OUTPUT_DIR      - Output directory (default: ./processed_invoices)")
        print("  INVOICELYZER_LOG_LEVEL       - Logging level (default: INFO)")
        print("  INVOICELYZER_DATABASE_URL    - PostgreSQL connection string (optional)")
        print("  INVOICELYZER_SAVE_JSON       - Save JSON files (default: true)")
        print("  INVOICELYZER_PROMPT_TEMPLATE - Custom prompt template path (optional)")
        sys.exit(1)
    
    # Get configuration
    config = get_config()
    
    # Setup logging
    logger = setup_logger(level=config['log_level'])
    
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

    