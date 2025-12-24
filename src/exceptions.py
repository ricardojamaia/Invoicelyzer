"""
Exception hierarchy for invoice processing.
Clear distinction between permanent and temporary failures.
"""


class InvoiceProcessingError(Exception):
    """Base exception for all invoice processing errors."""
    pass


# ============================================================================
# PERMANENT ERRORS - Will never succeed on retry
# ============================================================================

class PermanentError(InvoiceProcessingError):
    """
    Permanent failure that will never succeed on retry.
    
    Examples: 
        - Corrupted PDF structure
        - Invalid file format
        - Malformed data
        - Empty content
    
    Action: Log error, mark email as read, skip file.
    """
    pass


class PDFExtractionError(PermanentError):
    """Base class for PDF extraction permanent failures."""
    pass


class CorruptedPDFError(PDFExtractionError):
    """PDF structure is corrupted beyond repair."""
    pass


class EmptyPDFError(PDFExtractionError):
    """PDF has no extractable content."""
    pass


class EncryptedPDFError(PDFExtractionError):
    """PDF is encrypted and cannot be decrypted."""
    pass


class MalformedDataError(PermanentError):
    """Extracted data is malformed or cannot be parsed."""
    pass


# ============================================================================
# TEMPORARY ERRORS - Might succeed later
# ============================================================================

class TemporaryError(InvoiceProcessingError):
    """
    Temporary failure that might succeed on retry.
    
    Examples:
        - Network timeout
        - Service unavailable
        - Rate limit exceeded
        - Database connection lost
    
    Action: Log warning, keep email unread, retry later.
    """
    pass


class NetworkError(TemporaryError):
    """Network connection failed or timed out."""
    pass


class ServiceUnavailableError(TemporaryError):
    """External service (LLM, database) is temporarily unavailable."""
    pass


class DatabaseError(TemporaryError):
    """Database connection or query failed."""
    pass


class RateLimitError(TemporaryError):
    """Rate limit exceeded, need to wait before retrying."""
    pass


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_permanent_error(error: Exception) -> bool:
    """
    Check if error is permanent (shouldn't retry).
    
    Args:
        error: Exception instance
        
    Returns:
        True if permanent, False otherwise
    """
    return isinstance(error, PermanentError)


def is_temporary_error(error: Exception) -> bool:
    """
    Check if error is temporary (should retry).
    
    Args:
        error: Exception instance
        
    Returns:
        True if temporary, False otherwise
    """
    return isinstance(error, TemporaryError)
