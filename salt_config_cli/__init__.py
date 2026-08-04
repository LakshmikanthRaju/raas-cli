"""
Salt Config CLI - A Terraform-like CLI for VMware Aria Automation Config (Enterprise Salt)

This CLI provides infrastructure-as-code capabilities for managing Salt configurations
with a familiar plan/apply workflow similar to Terraform.
"""

__version__ = "0.5.0"
__author__ = "Salt Config CLI contributors"

from salt_config_cli.core.config import SaltConfigSettings
from salt_config_cli.core.state import StateManager

__all__ = [
    "__version__",
    "SaltConfigSettings",
    "StateManager",
]
