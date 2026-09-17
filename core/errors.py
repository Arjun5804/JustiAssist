from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

logger = logging.getLogger(__name__)

def add_exception_handlers(app: FastAPI):
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception at {request.url}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred while processing your request."}
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code >= 500:
            logger.error(f"HTTP {exc.status_code} error at {request.url}: {exc.detail}")
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": "An internal error occurred while processing your request."}
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
