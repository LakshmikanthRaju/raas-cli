"""
Core module containing configuration, state management, drift detection, and remediation.
"""

from salt_config_cli.core.config import SaltConfigSettings
from salt_config_cli.core.state import StateManager
from salt_config_cli.core.plan import PlanExecutor, Plan, ResourceChange
from salt_config_cli.core.drift import (
    DriftDetector,
    DriftReport,
    DriftStatus,
    ResourceDrift,
    RemediationPlan,
    RemediationAction,
)
from salt_config_cli.core.models import (
    Resource,
    ResourceType,
    TargetGroup,
    Job,
    Schedule,
    Pillar,
    StateFile,
)

__all__ = [
    "SaltConfigSettings",
    "StateManager",
    "PlanExecutor",
    "Plan",
    "ResourceChange",
    "DriftDetector",
    "DriftReport",
    "DriftStatus",
    "ResourceDrift",
    "RemediationPlan",
    "RemediationAction",
    "Resource",
    "ResourceType",
    "TargetGroup",
    "Job",
    "Schedule",
    "Pillar",
    "StateFile",
]
