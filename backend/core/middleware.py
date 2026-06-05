import uuid
import logging
from .middleware_utils import (
    set_request_id, set_trace_id, set_user_id, clear_request_context,
    get_request_id, get_trace_id, get_user_id
)

class RequestContextFilter(logging.Filter):
    """
    Logging filter that injects request correlation IDs into log records.
    """
    def filter(self, record):
        record.request_id = get_request_id()
        record.trace_id = get_trace_id()
        record.user_id = get_user_id()
        return True

class UserContextMiddleware:
    """
    Middleware that captures user ID after authentication has occurred.
    Should be placed AFTER AuthenticationMiddleware.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            set_user_id(str(request.user.id))
        
        return self.get_response(request)


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
            response = self.get_response(request)
            
            # 6. Return ID in response headers
            response['X-Request-ID'] = request_id
            return response
        finally:
            # 7. Always clear context to avoid leak between requests in threaded workers
            clear_request_context()

    def _is_valid_uuid(self, val: str) -> bool:
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, TypeError):
            return False
