"""
Custom exception handlers and error responses
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError
import logging
import traceback
from typing import Any, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class GalvanaException(Exception):
    """Base exception for Galvana API"""
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: str = "INTERNAL_ERROR",
        details: Dict[str, Any] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)

class ResourceNotFoundException(GalvanaException):
    """Resource not found exception"""
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} with ID {resource_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id}
        )

class SimulationException(GalvanaException):
    """Simulation-specific exception"""
    def __init__(self, message: str, run_id: str = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="SIMULATION_ERROR",
            details={"run_id": run_id} if run_id else {}
        )

class ValidationException(GalvanaException):
    """Input validation exception"""
    def __init__(self, message: str, field: str = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="VALIDATION_ERROR",
            details={"field": field} if field else {}
        )

class AuthenticationException(GalvanaException):
    """Authentication failed exception"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="AUTHENTICATION_FAILED"
        )

class AuthorizationException(GalvanaException):
    """Authorization failed exception"""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="AUTHORIZATION_FAILED"
        )

class RateLimitException(GalvanaException):
    """Rate limit exceeded exception"""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="RATE_LIMIT_EXCEEDED",
            details={"retry_after": retry_after}
        )

async def galvana_exception_handler(request: Request, exc: GalvanaException):
    """Handle Galvana-specific exceptions"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(
        f"{exc.error_code}: {exc.message}",
        extra={
            "request_id": request_id,
            "status_code": exc.status_code,
            "error_code": exc.error_code,
            "details": exc.details
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    errors = []
    for error in exc.errors():
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.warning(
        f"Validation error: {len(errors)} field(s) failed validation",
        extra={
            "request_id": request_id,
            "errors": errors
        }
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": errors},
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle standard HTTP exceptions"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail}",
        extra={
            "request_id": request_id,
            "status_code": exc.status_code
        }
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Log full traceback for debugging
    logger.error(
        f"Unexpected error: {str(exc)}",
        extra={
            "request_id": request_id,
            "traceback": traceback.format_exc()
        },
        exc_info=True
    )
    
    # NEVER expose internal details in production
    from services.api.config import settings
    
    # Sanitize error message for production
    if settings.environment == "production":
        message = "An internal error occurred. Please try again later."
        details = {"request_id": request_id}
    else:
        # Only show details in development
        message = f"{exc.__class__.__name__}: {str(exc)}"
        details = {
            "request_id": request_id,
            "exception": exc.__class__.__name__,
            "traceback": traceback.format_exc().split('\n')[-5:] if settings.debug else None
        }
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": message,
                "details": details,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    )

def register_exception_handlers(app):
    """Register all exception handlers with the FastAPI app"""
    app.add_exception_handler(GalvanaException, galvana_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)