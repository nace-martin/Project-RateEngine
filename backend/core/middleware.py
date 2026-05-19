import uuid
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


class RequestContextFilter(logging.Filter):
    """
    Logging filter that injects request correlation IDs into log records.
    """
    def filter(self, record):
        record.request_id = get_request_id()
        record.trace_id = get_trace_id()
        record.user_id = get_user_id()
        return True


class CorrelationIdMiddleware:
    """
    Middleware that ensures every request has a unique correlation ID.
    Supports incoming X-Request-ID and GCP's X-Cloud-Trace-Context.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Handle X-Request-ID
        request_id = request.headers.get('X-Request-ID')
        if not request_id or not self._is_valid_uuid(request_id):
            request_id = str(uuid.uuid4())
        
        # 2. Handle X-Cloud-Trace-Context (GCP standard)
        # Format: "TRACE_ID/SPAN_ID;o=TRACE_TRUE"
        trace_context = request.headers.get('X-Cloud-Trace-Context')
        trace_id = None
        if trace_context:
            trace_id = trace_context.split('/')[0]

        # 3. Store in context
        set_request_id(request_id)
        if trace_id:
            set_trace_id(trace_id)
        
        # 4. Attach to request object for downstream use
        request.request_id = request_id

        # 5. Process request
        try:
            # We can't set user_id here yet because authentication happens later in the middleware chain
            response = self.get_response(request)
            
            # 6. Inject user_id if authenticated
            if hasattr(request, 'user') and request.user.is_authenticated:
                set_user_id(str(request.user.id))
            
            # 7. Return ID in response headers
            response['X-Request-ID'] = request_id
            return response
        finally:
            # 8. Always clear context to avoid leak between requests in threaded workers
            clear_request_context()

    def _is_valid_uuid(self, val: str) -> bool:
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, TypeError):
            return False
