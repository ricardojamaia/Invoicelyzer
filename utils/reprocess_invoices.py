"""
Reprocess invoices - Re-run PDF extraction and catalog mapping.
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from sqlalchemy import select
from database import InvoiceDatabase
from database.models import Invoice
from main import get_config, create_invoice_processor, init_database, process_invoice_file


def reprocess_invoices(invoice_id=None, store=None, all_invoices=False, 
                       dry_run=False, continue_on_error=False):
    """
    Reprocess invoices through full extraction pipeline.
    
    Args:
        invoice_id: Process specific invoice ID
        store: Process all invoices from specific store
        all_invoices: Process all invoices
        dry_run: Preview without processing
        continue_on_error: Continue if some fail
    
    Returns:
        (success_count, failed_count)
    """
    # Get configuration and initialize components
    config = get_config()
    processor = create_invoice_processor(config)
    database = init_database(config)
    
    # Get PDF storage directory
    pdf_dir = Path(os.getenv('INVOICELYZER_PDF_STORAGE_DIR', config.get('pdf_storage_dir', './invoices')))
    
    if not pdf_dir.exists():
        raise ValueError(f"PDF directory does not exist: {pdf_dir}")
    
    # Get database connection for queries
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    if not db_url:
        raise ValueError("INVOICELYZER_DATABASE_URL not set")
    
    db = InvoiceDatabase(db_url)
    
    # Build query
    with db.session_manager.session() as session:
        query = select(Invoice)
        
        if invoice_id:
            query = query.where(Invoice.id == invoice_id)
        elif store:
            query = query.where(Invoice.store == store)
        elif not all_invoices:
            raise ValueError("Must specify invoice_id, store, or all_invoices=True")
        
        invoices = session.execute(query).scalars().all()
    
    total = len(invoices)
    print(f"Found {total} invoices")
    
    if total == 0:
        return 0, 0
    
    success = 0
    failed = 0
    
    for i, invoice in enumerate(invoices, 1):
        # Find PDF file
        pdf_path = _find_pdf(pdf_dir, invoice)
        
        if not pdf_path:
            print(f"[{i}/{total}] ✗ Invoice #{invoice.id}: PDF not found")
            failed += 1
            continue
        
        print(f"[{i}/{total}] Processing: {pdf_path.name}")
        
        if dry_run:
            print(f"  [DRY RUN] Would process: {pdf_path}")
            success += 1
            continue
        
        try:
            # Use the actual process_invoice_file function from main.py
            result = process_invoice_file(
                str(pdf_path),
                processor,
                database,
                config
            )
            
            if result:
                print(f"  ✓ Success")
                success += 1
            else:
                print(f"  ✗ Failed (permanent)")
                failed += 1
        
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed += 1
            
            if not continue_on_error:
                raise
    
    return success, failed


def _find_pdf(pdf_dir, invoice):
    """
    Find PDF file for invoice.
    
    Searches in this order:
    1. Direct absolute path from source_file
    2. Relative to pdf_dir
    3. In store subdirectory
    4. Recursively search all subdirectories
    """
    if not invoice.source_file:
        return None
    
    source_file = Path(invoice.source_file)
    
    # 1. Try direct absolute path
    if source_file.is_absolute() and source_file.exists():
        return source_file
    
    # 2. Try relative to pdf_dir
    path = pdf_dir / invoice.source_file
    if path.exists():
        return path
    
    # 3. Try with store subdirectory
    if invoice.store:
        path = pdf_dir / invoice.store.lower() / source_file.name
        if path.exists():
            return path
    
    # 4. Recursive search in all subdirectories
    # Search by filename only
    filename = source_file.name
    
    print(f"  Searching subdirectories for: {filename}")
    for pdf_file in pdf_dir.rglob(filename):
        if pdf_file.is_file():
            print(f"  Found: {pdf_file.relative_to(pdf_dir)}")
            return pdf_file
    
    # If still not found, try partial match (useful for numbered/dated files)
    # Search for files containing the invoice number or date
    if invoice.invoice_number:
        search_pattern = f"*{invoice.invoice_number}*.pdf"
        print(f"  Searching by invoice number: {search_pattern}")
        
        for pdf_file in pdf_dir.rglob(search_pattern):
            if pdf_file.is_file():
                print(f"  Found: {pdf_file.relative_to(pdf_dir)}")
                return pdf_file
    
    return None
