"""
Database management CLI
"""
import os
import sys
from database import InvoiceDatabase, SchemaManager

def main():
    db_url = os.getenv('INVOICELYZER_DATABASE_URL')
    
    if not db_url:
        print("Error: INVOICELYZER_DATABASE_URL not set")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("Usage: python db_cli.py <command>")
        print("\nCommands:")
        print("  create  - Create schema")
        print("  drop    - Drop schema (WARNING: deletes all data)")
        print("  reset   - Drop and recreate schema")
        print("  stats   - Show database statistics")
        sys.exit(1)
    
    command = sys.argv[1]
    schema = SchemaManager(db_url)
    db = InvoiceDatabase(db_url)
    
    if command == 'create':
        schema.create_schema()
        print("✓ Schema created")
    
    elif command == 'drop':
        confirm = input("This will delete ALL data. Type 'yes' to confirm: ")
        if confirm == 'yes':
            schema.drop_schema()
            print("✓ Schema dropped")
        else:
            print("Cancelled")
    
    elif command == 'reset':
        confirm = input("This will delete ALL data. Type 'yes' to confirm: ")
        if confirm == 'yes':
            schema.drop_schema()
            schema.create_schema()
            print("✓ Schema reset")
        else:
            print("Cancelled")
    
    elif command == 'stats':
        import psycopg2
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM invoices")
                invoice_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(*) FROM invoice_items")
                item_count = cur.fetchone()[0]
                
                cur.execute("SELECT COUNT(DISTINCT store) FROM invoices")
                store_count = cur.fetchone()[0]
                
                cur.execute("""
                    SELECT store, COUNT(*) 
                    FROM invoices 
                    GROUP BY store 
                    ORDER BY COUNT(*) DESC
                """)
                stores = cur.fetchall()
                
                print(f"\nDatabase Statistics:")
                print(f"  Total Invoices: {invoice_count}")
                print(f"  Total Items: {item_count}")
                print(f"  Stores: {store_count}")
                print(f"\nInvoices by Store:")
                for store, count in stores:
                    print(f"  {store}: {count}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()