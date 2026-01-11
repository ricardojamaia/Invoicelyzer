#!/usr/bin/env python3
"""
Invoicelyzer CLI - Unified command-line interface.

Usage:
    python utils/invoicelyzer-cli.py reprocess --all
    python utils/invoicelyzer-cli.py import --catalog catalog.csv --mappings mappings.csv
    python utils/invoicelyzer-cli.py schema --reset
"""
import sys
import os
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'src'))

import argparse
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def setup_logging(debug=False):
    """Configure logging based on debug flag."""
    level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' if debug else '%(message)s',
        force=True
    )
    
    if debug:
        print(f"Debug mode enabled")
        print(f"Project root: {project_root}")
        print(f"Python path: {sys.path[:3]}")
        print("")


def cmd_reprocess(args):
    """Reprocess PDFs through extraction pipeline."""
    from utils.reprocess_invoices import reprocess_invoices
    
    try:
        success, failed = reprocess_invoices(
            invoice_id=args.invoice_id,
            store=args.store,
            all_invoices=args.all,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error
        )
        
        print(f"\n{'='*60}")
        print(f"Complete: {success} success, {failed} failed")
        print(f"{'='*60}")
        
        return 0 if failed == 0 else 1
    
    except Exception as e:
        print(f"Error: {e}")
        if getattr(args, 'debug', False):
            import traceback
            traceback.print_exc()
        return 1


def cmd_import(args):
    """Import product catalog and mappings."""
    from utils.import_catalog import import_catalog
    
    if not args.catalog and not args.mappings:
        print("Error: Specify --catalog and/or --mappings")
        return 1
    
    try:
        catalog_count, mappings_count = import_catalog(
            catalog_file=args.catalog,
            mappings_file=args.mappings
        )
        
        print(f"\n{'='*60}")
        print(f"Import complete:")
        if args.catalog:
            print(f"  Catalog entries: {catalog_count}")
        if args.mappings:
            print(f"  Mappings: {mappings_count}")
        print(f"{'='*60}")
        
        return 0
    
    except Exception as e:
        print(f"Error: {e}")
        if getattr(args, 'debug', False):
            import traceback
            traceback.print_exc()
        return 1


def cmd_schema(args):
    """Schema operations: create, delete, reset."""
    from utils.schema_manager import create_schema, delete_schema, reset_schema
    
    if not args.create and not args.delete and not args.reset:
        print("Error: Specify --create, --delete, or --reset")
        return 1
    
    try:
        if args.create:
            create_schema()
        elif args.delete:
            delete_schema()
        elif args.reset:
            reset_schema()
        
        return 0
    
    except Exception as e:
        print(f"Error: {e}")
        if getattr(args, 'debug', False):
            import traceback
            traceback.print_exc()
        return 1


def main():
    parser = argparse.ArgumentParser(
        description='Invoicelyzer CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reprocess all invoices
  python utils/invoicelyzer-cli.py reprocess --all
  
  # Import catalog and mappings
  python utils/invoicelyzer-cli.py import --catalog data/catalog.csv --mappings data/mappings.csv
  
  # Reset database schema
  python utils/invoicelyzer-cli.py schema --reset
  
  # Enable debug mode
  python utils/invoicelyzer-cli.py reprocess --all --debug
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Reprocess command
    reprocess = subparsers.add_parser(
        'reprocess',
        help='Reprocess PDFs through extraction pipeline'
    )
    reprocess.add_argument('--all', action='store_true', help='Process all invoices')
    reprocess.add_argument('--invoice-id', type=int, metavar='ID', help='Process specific invoice')
    reprocess.add_argument('--store', metavar='NAME', help='Process specific store')
    reprocess.add_argument('--dry-run', action='store_true', help='Preview only')
    reprocess.add_argument('--continue-on-error', action='store_true', help='Continue on errors')
    reprocess.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # Import command
    import_cmd = subparsers.add_parser(
        'import',
        help='Import product catalog and mappings'
    )
    import_cmd.add_argument('--catalog', metavar='FILE', help='Catalog CSV file')
    import_cmd.add_argument('--mappings', metavar='FILE', help='Mappings CSV file')
    import_cmd.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # Schema command
    schema = subparsers.add_parser(
        'schema',
        help='Database schema operations'
    )
    schema.add_argument('--create', action='store_true', help='Create schema')
    schema.add_argument('--delete', action='store_true', help='Delete schema')
    schema.add_argument('--reset', action='store_true', help='Reset schema')
    schema.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(debug=getattr(args, 'debug', False))
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == 'reprocess':
            return cmd_reprocess(args)
        elif args.command == 'import':
            return cmd_import(args)
        elif args.command == 'schema':
            return cmd_schema(args)
    
    except KeyboardInterrupt:
        print("\nCancelled")
        return 130


if __name__ == '__main__':
    sys.exit(main())
