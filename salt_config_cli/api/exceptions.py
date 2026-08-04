"""
Custom exceptions for Salt Config CLI API operations.
"""

from typing import Any, Dict, Optional


class APIError(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self, 
        message: str, 
        code: Optional[int] = None,
        detail: Optional[str] = None,
        response: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail
        self.response = response
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.insert(0, f"[{self.code}]")
        if self.detail:
            parts.append(f"({self.detail})")
        return " ".join(parts)


class AuthenticationError(APIError):
    """Raised when authentication fails."""
    pass


class ConnectionError(APIError):
    """Raised when connection to server fails."""
    pass


class NotFoundError(APIError):
    """Raised when a resource is not found."""
    pass


class ValidationError(APIError):
    """Raised when request validation fails."""
    pass


class TimeoutError(APIError):
    """Raised when a request times out."""
    pass


class RateLimitError(APIError):
    """Raised when rate limit is exceeded."""
    pass


class ServerError(APIError):
    """Raised for 5xx server errors."""
    pass
