import logging
from threading import local
from typing import Optional

# Thread-local storage for request-specific context
_context = local()

logger = logging.getLogger(__name__)

def set_request_id(request_id: str):
    """Store the request ID in the current thread's context."""
    _context.request_id = request_id

def get_request_id() -> Optional[str]:
    """Retrieve the request ID from the current thread's context."""
    return getattr(_context, 'request_id', None)

def set_trace_id(trace_id: str):
    """Store the GCP trace ID in the current thread's context."""
    _context.trace_id = trace_id

def get_trace_id() -> Optional[str]:
    """Retrieve the GCP trace ID from the current thread's context."""
    return getattr(_context, 'trace_id', None)

def set_user_id(user_id: str):
    """Store the authenticated user ID in the current thread's context."""
    _context.user_id = user_id

def get_user_id() -> Optional[str]:
    """Retrieve the user ID from the current thread's context."""
    return getattr(_context, 'user_id', None)

def clear_request_context():
    """Clear all request-specific data from thread-local storage."""
    if hasattr(_context, 'request_id'):
        del _context.request_id
    if hasattr(_context, 'trace_id'):
        del _context.trace_id
    if hasattr(_context, 'user_id'):
        del _context.user_id
