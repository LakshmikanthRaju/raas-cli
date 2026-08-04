"""
Resource handlers for Salt Config CLI.

Each handler implements CRUD operations for a specific resource type.
"""

from salt_config_cli.handlers.target_group import TargetGroupHandler
from salt_config_cli.handlers.job import JobHandler
from salt_config_cli.handlers.pillar import PillarHandler
from salt_config_cli.handlers.state_file import StateFileHandler

__all__ = [
    "TargetGroupHandler",
    "JobHandler",
    "PillarHandler",
    "StateFileHandler",
]
