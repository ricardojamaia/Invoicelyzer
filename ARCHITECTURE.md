# Architecture Overview

Invoicelyzer is a modular invoice processing system that extracts structured data from PDF invoices using LLM technology and maps products to a standardized catalog.

## System Overview

```
┌─────────────┐
│ PDF Invoice │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         Invoice Processor               │
│  ┌────────┐  ┌──────────┐  ┌─────────┐  │
│  │ Parser │→ │ Analyzer │→ │ Mapper  │  │
│  └────────┘  └──────────┘  └─────────┘  │
└──────────────────┬──────────────────────┘
                   │
                   ▼
           ┌──────────────┐
           │ Structured   │
           │ Invoice Data │
           └──────────────┘
```

## Core Components

### 1. Parser (`parser.py`)
**Purpose**: Extract text from PDF files

**Responsibilities**:
- Validate PDF file integrity
- Extract text from all pages
- Handle corrupted or encrypted PDFs
- Provide specific error types for different failure modes

**Key Features**:
- Forgiving header validation (logs warnings but continues)
- Page-by-page extraction with partial failure handling
- Specific exception types (`CorruptedPDFError`, `EmptyPDFError`, `EncryptedPDFError`)

**Dependencies**: `pypdf`

### 2. Analyzer (`analyzer.py`)
**Purpose**: Convert raw text to structured invoice data

**Responsibilities**:
- Send invoice text to LLM
- Parse LLM response into structured format
- Extract invoice metadata (date, store, total, etc.)
- Extract line items with quantities and prices

**Output Format**:
```json
{
  "store": "Store Name",
  "invoice_date": "2024-01-15",
  "total": 123.45,
  "items": [
    {
      "name": "Product Name",
      "quantity": 2,
      "unit_price": 10.00,
      "total_price": 20.00
    }
  ]
}
```

**Dependencies**: LLM service (Ollama)

### 3. ProductCatalog (Abstract Interface)
**Purpose**: Define contract for product catalog access

**Interface**:
```python
class ProductCatalog(ABC):
    @abstractmethod
    def get_all_products(self) -> List[Dict[str, str]]:
        """Return list of {category, product_name}"""
        
    @abstractmethod
    def get_known_mapping(self, original_name: str) -> Optional[Dict]:
        """Return known mapping or None"""
        
    @abstractmethod
    def get_all_known_mappings(self) -> Dict[str, Dict]:
        """Return all known mappings"""
```

**Why Abstract**: Enables different catalog sources (database, file, API) without changing mapper logic

### 4. DatabaseProductCatalog (`database_product_catalog.py`)
**Purpose**: PostgreSQL implementation of ProductCatalog

**Responsibilities**:
- Query `product_catalog` table for available products
- Query `product_mappings` table for known mappings
- Implement ProductCatalog interface

**Database Schema**:
```sql
product_catalog (
  category VARCHAR,
  product_name VARCHAR
)

product_mappings (
  original_name VARCHAR,
  catalog_product VARCHAR,
  catalog_category VARCHAR,
  confidence VARCHAR
)
```

### 5. ProductMapper (`mapper.py`)
**Purpose**: Map invoice items to catalog products

**Algorithm** (3-tier approach):

1. **Exact Match** (Priority 1, ~100% accuracy)
   - Normalize product name
   - Check against known mappings
   - Return immediately if found

2. **Partial Match** (Priority 2, ~90% accuracy)
   - Substring matching with keyword overlap
   - Requires ≥50% keyword similarity
   - Returns confidence score

3. **ML Match** (Priority 3, 48-70% accuracy)
   - TF-IDF + Cosine Similarity
   - Jaccard similarity on keywords
   - Combined score: `0.6 * cosine + 0.4 * jaccard`
   - Configurable threshold (default: 0.4)

**Normalization Process**:
- Remove units (KG, G, ML, etc.)
- Remove codes (CNT, EMB, IGP, etc.)
- Remove stopwords (DE, DA, DO, etc.)
- Uppercase and clean special characters

**Dependencies**: ProductCatalog interface

### 6. InvoiceProcessor (`processor.py`)
**Purpose**: Orchestrate the complete processing pipeline

**Pipeline**:
```
PDF → Parser → Text → Analyzer → Invoice Data → Mapper → Enhanced Data
```

**Responsibilities**:
- Coordinate parser, analyzer, and mapper
- Handle exceptions and error propagation
- Add processing metadata
- Return final structured data

**Exception Handling**:
- Re-raises `PermanentError` for corrupted PDFs
- Re-raises `TemporaryError` for service outages
- Continues on non-critical mapper failures

**Dependencies**: Parser, Analyzer, Mapper (injected)

### 7. EmailMonitor (`email_monitor.py`)
**Purpose**: Monitor email for invoice attachments

**Responsibilities**:
- Connect to IMAP server
- Check for unread emails
- Download PDF attachments
- Invoke processing callback
- Mark emails as read based on callback result

**Callback Protocol**:
```python
def callback(pdf_path: str, sender: str) -> bool:
    """
    Process PDF from email.
    Returns True to mark as read, False to keep unread.
    """
```

**Smart Retry Logic**:
- `True` return → Email marked as read (permanent success/failure)
- `False` return → Email kept unread (temporary failure, will retry)

**Dependencies**: `imap_tools`

### 8. InvoiceDatabase (`database/database.py`)
**Purpose**: Persist invoice data to PostgreSQL

**Responsibilities**:
- Save invoices and line items
- Handle upserts (update if exists)
- Query invoices by various criteria
- Maintain referential integrity

**Schema**:
```sql
invoices (
  id SERIAL PRIMARY KEY,
  store VARCHAR,
  invoice_date DATE,
  total DECIMAL,
  ...
)

invoice_items (
  id SERIAL PRIMARY KEY,
  invoice_id INTEGER REFERENCES invoices(id),
  name VARCHAR,
  quantity DECIMAL,
  unit_price DECIMAL,
  total_price DECIMAL,
  catalog_product_name VARCHAR,
  catalog_category VARCHAR,
  ...
)
```

## Design Principles

### Dependency Injection
Components receive their dependencies rather than creating them:

```python
# ✅ Good: Dependencies injected
parser = PDFTextExtractor()
analyzer = InvoiceAnalyzer(llm_url, model)
mapper = ProductMapper(catalog)
processor = InvoiceProcessor(parser, analyzer, mapper)

# ❌ Bad: Component creates dependencies
processor = InvoiceProcessor(llm_url, model, db_url, ...)
# Creates its own parser, analyzer, mapper internally
```

**Benefits**:
- Easy to test with mocks
- Easy to swap implementations
- Clear dependency graph

### Single Responsibility
Each component has one clear purpose:

| Component | Responsibility |
|-----------|---------------|
| Parser | Extract text from PDF |
| Analyzer | Convert text to structure |
| Mapper | Map products to catalog |
| Processor | Orchestrate pipeline |
| EmailMonitor | Monitor emails |
| Database | Store data |

### Interface Segregation
Abstract interfaces enable multiple implementations:

```python
# Abstract interface
class ProductCatalog(ABC):
    def get_all_products(self): ...

# Different implementations
catalog = DatabaseProductCatalog(db_url)      # PostgreSQL
catalog = FileCatalog('products.csv')         # CSV file
catalog = APICatalog('https://api.com')       # REST API

# Mapper works with any implementation
mapper = ProductMapper(catalog)
```

### Exception Hierarchy
Clear distinction between permanent and temporary failures:

```
InvoiceProcessingError
├── PermanentError (don't retry)
│   ├── CorruptedPDFError
│   ├── EmptyPDFError
│   └── EncryptedPDFError
└── TemporaryError (retry later)
    ├── NetworkError
    ├── ServiceUnavailableError
    └── DatabaseError
```

**Usage**:
```python
try:
    invoice_data = processor.process(pdf_path)
except PermanentError:
    # Mark email as read, log error, skip
    return None
except TemporaryError:
    # Keep email unread, will retry
    raise
```

## Data Flow

### Batch Processing Flow

```
main.py
  │
  ├─ Create components
  │  ├─ parser = PDFTextExtractor()
  │  ├─ analyzer = InvoiceAnalyzer(llm_url, model)
  │  ├─ catalog = DatabaseProductCatalog(db_url)
  │  ├─ mapper = ProductMapper(catalog, use_ml=True)
  │  ├─ processor = InvoiceProcessor(parser, analyzer, mapper)
  │  └─ database = InvoiceDatabase(db_url)
  │
  └─ For each PDF
     ├─ invoice_data = processor.process(pdf_path)
     ├─ database.save_invoice(invoice_data)
     └─ save_invoice_json(invoice_data, output_dir)
```

### Email Monitoring Flow

```
main.py
  │
  ├─ Create components (same as batch)
  │
  ├─ email_monitor = EmailMonitor(imap, email, password, pdf_dir)
  │
  ├─ Define callback
  │  def callback(pdf_path, sender):
  │    invoice_data = processor.process(pdf_path)
  │    database.save_invoice(invoice_data)
  │    return True  # Mark as read
  │
  └─ monitor.check_new_emails(callback)
     │
     └─ For each unread email
        ├─ Download PDF attachments
        ├─ Call callback(pdf_path, sender)
        └─ Mark as read if callback returns True
```

## Extension Points

### Adding New Catalog Source

Implement the `ProductCatalog` interface:

```python
class APICatalog(ProductCatalog):
    def __init__(self, api_url: str):
        self.api_url = api_url
    
    def get_all_products(self) -> List[Dict[str, str]]:
        response = requests.get(f'{self.api_url}/products')
        return response.json()
    
    def get_known_mapping(self, original_name: str) -> Optional[Dict]:
        response = requests.get(
            f'{self.api_url}/mapping',
            params={'name': original_name}
        )
        return response.json() if response.ok else None
    
    def get_all_known_mappings(self) -> Dict[str, Dict]:
        response = requests.get(f'{self.api_url}/mappings')
        return response.json()

# Use it
catalog = APICatalog('https://api.example.com')
mapper = ProductMapper(catalog)
# Everything else stays the same
```

### Adding New Storage Backend

Implement storage interface and inject it:

```python
class S3Storage:
    def save_invoice(self, invoice_data: Dict, pdf_path: str):
        # Save to S3
        key = f"invoices/{invoice_data['store']}/{filename}.json"
        s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(invoice_data))

# In main.py
storage = S3Storage(bucket_name='my-invoices')

# In callback
def callback(pdf_path, sender):
    invoice_data = processor.process(pdf_path)
    storage.save_invoice(invoice_data, pdf_path)
    return True
```

### Adding Custom Analyzers

Swap the analyzer component:

```python
class CustomAnalyzer:
    def analyze(self, text: str, context: Optional[Dict] = None) -> Dict:
        # Custom analysis logic
        return invoice_data

# Use it
analyzer = CustomAnalyzer()
processor = InvoiceProcessor(parser, analyzer, mapper)
```

## Configuration

Environment variables control system behavior:

```bash
# LLM Configuration
INVOICELYZER_LLM_URL=http://localhost:11434
INVOICELYZER_LLM_MODEL=qwen2.5:14b

# Database
INVOICELYZER_DATABASE_URL=postgresql://user:pass@host/db

# Product Mapping
INVOICELYZER_ENABLE_MAPPING=true
INVOICELYZER_MAPPING_USE_ML=true
INVOICELYZER_MAPPING_ML_THRESHOLD=0.4

# Output
INVOICELYZER_OUTPUT_DIR=./processed_invoices
INVOICELYZER_SAVE_JSON=true

# Email Monitoring
INVOICELYZER_EMAIL_ENABLED=false
INVOICELYZER_EMAIL_IMAP_SERVER=imap.gmail.com
INVOICELYZER_EMAIL_ADDRESS=your-email@gmail.com
INVOICELYZER_EMAIL_PASSWORD=your-password
INVOICELYZER_EMAIL_CHECK_INTERVAL=300
INVOICELYZER_PDF_STORAGE_DIR=./invoices
```

## Testing

### Unit Testing with Mocks

```python
# test_mapper.py
class MockCatalog(ProductCatalog):
    def get_all_products(self):
        return [
            {'category': 'Fruits', 'product_name': 'Orange'},
            {'category': 'Meat', 'product_name': 'Chicken'}
        ]
    
    def get_known_mapping(self, original_name):
        if 'ORANGE' in original_name.upper():
            return {
                'product_name': 'Orange',
                'category': 'Fruits',
                'confidence': 'Manual'
            }
        return None
    
    def get_all_known_mappings(self):
        return {}

# Test without database
catalog = MockCatalog()
mapper = ProductMapper(catalog)
result = mapper.map_product('ORANGE KG')
assert result['product'] == 'Orange'
assert result['category'] == 'Fruits'
```

### Integration Testing

```python
# test_integration.py
def test_full_pipeline():
    # Real components
    parser = PDFTextExtractor()
    analyzer = InvoiceAnalyzer('http://localhost:11434', 'qwen2.5:14b')
    
    # Mock catalog for testing
    catalog = MockCatalog()
    mapper = ProductMapper(catalog)
    
    # Create processor
    processor = InvoiceProcessor(parser, analyzer, mapper)
    
    # Test with real PDF
    result = processor.process('test_invoice.pdf')
    
    # Verify structure
    assert 'store' in result
    assert 'items' in result
    assert len(result['items']) > 0
    assert 'catalog_product_name' in result['items'][0]
```

## Performance Considerations

### Mapper Performance
- ML matching is slower than exact/partial matching
- Disable ML if catalog is comprehensive: `use_ml=False`
- Adjust ML threshold for speed/accuracy tradeoff
- Pre-trained features cached for all catalog products

### Database Performance
- Upserts use unique constraints for efficiency
- Bulk inserts for items use `executemany`
- Indexes on frequently queried fields

### LLM Performance
- Processing time dominated by LLM inference (~5-15s per invoice)
- Use faster models for speed: `llama3.2:3b`
- Use better models for accuracy: `qwen2.5:14b`

## Security Considerations

### Email Credentials
- Never commit credentials to version control
- Use environment variables or secret management
- Support app-specific passwords for Gmail

### Database Access
- Use connection pooling for concurrent access
- Parameterized queries prevent SQL injection
- Schema migrations use transactions

### PDF Processing
- Sandboxed PDF parsing with pypdf
- File size limits prevent memory exhaustion
- Timeout handling for large files

## Deployment

### Docker Deployment

```yaml
services:
  invoicelyzer-monitor:
    build: .
    environment:
      - INVOICELYZER_LLM_URL=http://invoicelyzer-ollama:11434
      - INVOICELYZER_DATABASE_URL=postgresql://user:pass@postgres/db
    volumes:
      - ./invoices:/data/invoices
    depends_on:
      - postgres
      - invoicelyzer-ollama
```

### Standalone Deployment

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
export INVOICELYZER_LLM_URL=http://localhost:11434
export INVOICELYZER_DATABASE_URL=postgresql://...

# Run batch processing
python src/main.py /path/to/invoices/*.pdf

# Run email monitoring
python src/main.py --email
```

## Architecture Decisions

### Why Dependency Injection?
- **Testability**: Easy to mock components
- **Flexibility**: Swap implementations without code changes
- **Clarity**: Explicit dependency graph

### Why Abstract ProductCatalog?
- **Multiple Sources**: Database, file, API all possible
- **Testing**: Mock catalog for unit tests
- **Future-Proof**: Add new sources without changing mapper

### Why Exception Hierarchy?
- **Smart Retries**: Automatic based on exception type
- **Clear Intent**: Error type = recovery strategy
- **No String Parsing**: Type-safe error handling

### Why EmailMonitor Callback?
- **Separation**: Email logic separate from processing
- **Flexibility**: Different callbacks for different use cases
- **Testability**: Mock callbacks for email tests

## Future Enhancements

### Planned Features
- OCR support for scanned invoices
- Multi-language support
- Batch import from cloud storage (S3, Google Drive)
- Web UI for monitoring and management
- Advanced analytics and reporting

### Extension Opportunities
- Custom LLM fine-tuning for specific stores
- Active learning for product mappings
- Parallel processing for large batches
- Real-time processing webhooks

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and pull request process.

## License

See [LICENSE](LICENSE) for license information.
