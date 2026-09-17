import json
import logging
import uuid
from datetime import datetime
from contextvars import ContextVar

# Context variable to hold the current request ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

class RequestCorrelationMiddleware:
    """
    Pure ASGI Middleware to ensure every request has a unique request ID.
    Reads X-Request-ID if present and safe, otherwise generates a UUID4.
    Exposes the ID in the X-Request-ID response header and to logs via ContextVar.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract headers (which are list of byte tuples)
        headers = scope.get("headers", [])
        req_id = ""
        for k, v in headers:
            if k.lower() == b"x-request-id":
                req_id = v.decode("latin-1")
                break

        # Conservatively validate incoming request IDs (alphanumeric and dashes, max 64 chars)
        if not req_id or len(req_id) > 64 or not req_id.replace("-", "").isalnum():
            req_id = str(uuid.uuid4())
            
        token = correlation_id_var.set(req_id)

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                # Add X-Request-ID to response headers
                headers = list(message.get("headers", []))
                # Check if it already exists to avoid duplicates
                if not any(k.lower() == b"x-request-id" for k, v in headers):
                    headers.append((b"x-request-id", req_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # Ensure the ContextVar is cleaned up after request
            correlation_id_var.reset(token)

class JSONLogFormatter(logging.Formatter):
    """
    Structured JSON formatter for production application logs.
    Includes request_id from ContextVar when available.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        req_id = correlation_id_var.get()
        if req_id:
            log_entry["request_id"] = req_id
            
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        # Prevent serialization of any obvious sensitive info in extra fields if they were added
        # JustiAssist standard is to not attach sensitive kwargs, but we keep this dictionary clean.
        
        return json.dumps(log_entry, default=str)

class ContextFilter(logging.Filter):
    """Injects request_id into standard log records for human-readable output."""
    def filter(self, record):
        record.request_id = correlation_id_var.get()
        return True

def setup_logging(app_env: str = "development"):
    """
    Configures the root logger.
    Production: JSON logs.
    Development: Human-readable logs with request ID.
    """
    root_logger = logging.getLogger()
    
    # Prevent duplicate JustiAssist handlers without clearing Uvicorn handlers
    has_ja_handler = any(
        isinstance(h, logging.StreamHandler) and (
            isinstance(h.formatter, JSONLogFormatter) or
            any(isinstance(f, ContextFilter) for f in h.filters)
        )
        for h in root_logger.handlers
    )
    
    if has_ja_handler:
        return
        
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    
    if app_env == "production":
        handler.setFormatter(JSONLogFormatter())
    else:
        # Development human-readable formatting
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s] [req:%(request_id)s] %(message)s'
        )
        handler.setFormatter(formatter)
        handler.addFilter(ContextFilter())
        
    root_logger.addHandler(handler)

    # Suppress verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
