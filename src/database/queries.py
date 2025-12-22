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
    catalog_product_name VARCHAR(500),
    catalog_category VARCHAR(255),
    mapping_confidence VARCHAR(50),
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

CREATE_INDEX_ITEMS_CATALOG_PRODUCT = """
CREATE INDEX IF NOT EXISTS idx_items_catalog_product ON invoice_items(catalog_product_name);
"""

CREATE_INDEX_ITEMS_CATALOG_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_items_catalog_category ON invoice_items(catalog_category);
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
SELECT id, name, category, quantity, unit_price, total_price, 
       catalog_product_name, catalog_category, mapping_confidence,
       created_at, updated_at
FROM invoice_items
WHERE invoice_id = %s
ORDER BY id
"""

INSERT_ITEM = """
INSERT INTO invoice_items (
    invoice_id, name, category, quantity, unit_price, total_price,
    catalog_product_name, catalog_category, mapping_confidence
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""

UPDATE_ITEM = """
UPDATE invoice_items SET
    category = %s,
    quantity = %s,
    unit_price = %s,
    total_price = %s,
    catalog_product_name = %s,
    catalog_category = %s,
    mapping_confidence = %s,
    updated_at = CURRENT_TIMESTAMP
WHERE id = %s
"""

DELETE_ITEMS = """
DELETE FROM invoice_items
WHERE id = ANY(%s)
"""

# Product catalog queries
CREATE_CATALOG_TABLE = """
CREATE TABLE IF NOT EXISTS product_catalog (
    id SERIAL PRIMARY KEY,
    category VARCHAR(255) NOT NULL,
    product_name VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, product_name)
);
"""

CREATE_INDEX_CATALOG_PRODUCT = """
CREATE INDEX IF NOT EXISTS idx_catalog_product ON product_catalog(product_name);
"""

CREATE_INDEX_CATALOG_CATEGORY = """
CREATE INDEX IF NOT EXISTS idx_catalog_category ON product_catalog(category);
"""

INSERT_CATALOG_ITEM = """
INSERT INTO product_catalog (category, product_name)
VALUES (%s, %s)
ON CONFLICT (category, product_name) DO NOTHING;
"""

GET_CATALOG_ITEMS = """
SELECT id, category, product_name FROM product_catalog ORDER BY category, product_name;
"""

# Known mappings queries
CREATE_MAPPINGS_TABLE = """
CREATE TABLE IF NOT EXISTS product_mappings (
    id SERIAL PRIMARY KEY,
    original_name VARCHAR(500) NOT NULL,
    catalog_product VARCHAR(500) NOT NULL,
    catalog_category VARCHAR(255) NOT NULL,
    confidence VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(original_name)
);
"""

CREATE_INDEX_MAPPINGS_ORIGINAL = """
CREATE INDEX IF NOT EXISTS idx_mappings_original ON product_mappings(original_name);
"""

INSERT_MAPPING = """
INSERT INTO product_mappings (original_name, catalog_product, catalog_category, confidence)
VALUES (%s, %s, %s, %s)
ON CONFLICT (original_name) 
DO UPDATE SET 
    catalog_product = EXCLUDED.catalog_product,
    catalog_category = EXCLUDED.catalog_category,
    confidence = EXCLUDED.confidence,
    updated_at = CURRENT_TIMESTAMP;
"""

GET_MAPPING = """
SELECT catalog_product, catalog_category, confidence 
FROM product_mappings 
WHERE original_name = %s;
"""

GET_ALL_MAPPINGS = """
SELECT original_name, catalog_product, catalog_category, confidence 
FROM product_mappings 
ORDER BY original_name;
"""
