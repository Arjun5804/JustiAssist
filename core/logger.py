import json
import logging
import uuid
from datetime import datetime
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Context variable to hold the current request ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to ensure every request has a unique request ID.
    Reads X-Request-ID if present and safe, otherwise generates a UUID4.
    Exposes the ID in the X-Request-ID response header and to logs via ContextVar.
    """
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", "")
        # Conservatively validate incoming request IDs (alphanumeric and dashes, max 64 chars)
        if not req_id or len(req_id) > 64 or not req_id.replace("-", "").isalnum():
            req_id = str(uuid.uuid4())
            
        token = correlation_id_var.set(req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
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
    
    # Prevent duplicate handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
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
