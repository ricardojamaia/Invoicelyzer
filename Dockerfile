FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY config/ ./config/

# Create directories for data
RUN mkdir -p /data/invoices /data/processed_invoices /data/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run as non-root user
# RUN useradd -m -u 1000 invoicelyzer && \
#     chown -R invoicelyzer:invoicelyzer /app /data
# USER invoicelyzer

# Default command (can be overridden)
CMD ["python", "src/main.py", "--monitor-email"]