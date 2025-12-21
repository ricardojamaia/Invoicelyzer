"""
File storage operations for invoice data.
Handles saving invoices in various formats.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("invoice_processor.storage")


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


def save_invoice_json(
    invoice_data: Dict, 
    output_dir: str, 
    source_pdf_path: Optional[str] = None
) -> str:
    """
    Save processed invoice to JSON file.
    Overwrites existing files.
    
    Args:
        invoice_data: Structured invoice data
        output_dir: Directory to save output
        source_pdf_path: Original PDF path (to derive JSON filename), optional
        
    Returns:
        Path to saved file
    """
    # Create output directory if needed
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Determine filename
    if source_pdf_path is not None:
        # Use PDF filename as base
        pdf_name = Path(source_pdf_path).stem
        filename = f"{pdf_name}.json"
        logger.debug(f"Using PDF-based filename: {filename}")
    else:
        # Fallback to generating from invoice data
        store = sanitize_filename(invoice_data.get('store', 'unknown').lower())
        date = invoice_data.get('date', 'nodate').replace('-', '')
        
        invoice_num = invoice_data.get('invoice_number')
        if invoice_num and invoice_num != 'null':
            invoice_num = sanitize_filename(str(invoice_num))
        else:
            invoice_num = 'noinv'
        
        filename = f"{store}_{date}_{invoice_num}.json"
        logger.debug(f"Generated filename: {filename}")
    
    filepath = output_path / filename
    
    # Always save (overwrite if exists)
    if filepath.exists():
        logger.info(f"Overwriting existing JSON: {filepath}")
    else:
        logger.debug(f"Creating new JSON: {filepath}")
    
    # Save JSON
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(invoice_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Invoice saved to: {filepath}")
    return str(filepath)
