"""
API client module for VMware Aria Automation Config (Enterprise Salt).

Provides HTTP client and resource-specific API wrappers.
"""

from salt_config_cli.api.client import AriaConfigClient
from salt_config_cli.api.exceptions import (
    APIError,
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    ValidationError,
)

__all__ = [
    "AriaConfigClient",
    "APIError",
    "AuthenticationError",
    "ConnectionError",
    "NotFoundError",
    "ValidationError",
]
