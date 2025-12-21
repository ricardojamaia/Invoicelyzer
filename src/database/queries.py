"""
SQL queries for invoice database operations.
All queries are defined as constants for easy maintenance and testing.
"""

# Schema queries
CREATE_INVOICES_TABLE = """
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    store VARCHAR(255) NOT NULL,
    location TEXT,
    invoice_date DATE NOT NULL,
    invoice_time TIME,
    total DECIMAL(10, 2),
    payment_method VARCHAR(100),
    invoice_number VARCHAR(100),
    source_file VARCHAR(500),
    raw_text_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store, invoice_date, invoice_number)
);
"""

CREATE_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS invoice_items (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    category VARCHAR(255),
    quantity DECIMAL(10, 3),
    unit_price DECIMAL(10, 2),
    total_price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Indexes
CREATE_INDEX_INVOICES_STORE = """
CREATE INDEX IF NOT EXISTS idx_invoices_store ON invoices(store);
"""

CREATE_INDEX_INVOICES_DATE = """
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
"""

CREATE_INDEX_ITEMS_INVOICE = """
CREATE INDEX IF NOT EXISTS idx_items_invoice ON invoice_items(invoice_id);
"""

CREATE_INDEX_ITEMS_NAME = """
CREATE INDEX IF NOT EXISTS idx_items_name ON invoice_items(name);
"""

CREATE_INDEX_ITEMS_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_items_category ON invoice_items(category);
"""

CREATE_INDEX_ITEMS_INVOICE_NAME = """
CREATE INDEX IF NOT EXISTS idx_items_invoice_name ON invoice_items(invoice_id, name);
"""

# Invoice queries
CHECK_INVOICE_EXISTS = """
SELECT id FROM invoices 
WHERE store = %s 
  AND invoice_date = %s 
  AND invoice_number = %s
"""

INSERT_INVOICE = """
INSERT INTO invoices (
    store, location, invoice_date, invoice_time, 
    total, payment_method, invoice_number, 
    source_file, raw_text_length
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s
)
RETURNING id;
"""

UPDATE_INVOICE = """
UPDATE invoices SET
    location = %s,
    invoice_time = %s,
    total = %s,
    payment_method = %s,
    source_file = %s,
    raw_text_length = %s,
    updated_at = CURRENT_TIMESTAMP
WHERE id = %s
"""

GET_INVOICE = """
SELECT 
    id, store, location, invoice_date, invoice_time,
    total, payment_method, invoice_number,
    source_file, raw_text_length, created_at, updated_at
FROM invoices
WHERE id = %s
"""

SEARCH_INVOICES = """
SELECT 
    id, store, location, invoice_date, invoice_time,
    total, payment_method, invoice_number,
    source_file, raw_text_length, created_at, updated_at
FROM invoices
WHERE 1=1
"""

# Item queries
GET_INVOICE_ITEMS = """
SELECT id, name, category, quantity, unit_price, total_price, created_at, updated_at
FROM invoice_items
WHERE invoice_id = %s
ORDER BY id
"""

INSERT_ITEM = """
INSERT INTO invoice_items (
    invoice_id, name, category, quantity, unit_price, total_price
) VALUES (
    %s, %s, %s, %s, %s, %s
)
"""

UPDATE_ITEM = """
UPDATE invoice_items SET
    category = %s,
    quantity = %s,
    unit_price = %s,
    total_price = %s,
    updated_at = CURRENT_TIMESTAMP
WHERE id = %s
"""

DELETE_ITEMS = """
DELETE FROM invoice_items
WHERE id = ANY(%s)
"""