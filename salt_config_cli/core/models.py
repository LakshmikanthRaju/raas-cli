"""
Core data models for Salt Config CLI resources.

These models represent the various resource types that can be managed
through VMware Aria Automation Config (Enterprise Salt).
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime


class ResourceType(str, Enum):
    """Enumeration of supported Salt resource types."""
    
    TARGET_GROUP = "target_group"
    JOB = "job"
    SCHEDULE = "schedule"
    PILLAR = "pillar"
    STATE_FILE = "state_file"
    MINION = "minion"
    MASTER = "master"
    ROLE = "role"
    USER = "user"
    ENVIRONMENT = "environment"
    MINION_STATE = "minion_state"  # For drift detection on minion configurations


class ChangeAction(str, Enum):
    """Types of changes that can be made to resources."""
    
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_OP = "no-op"
    READ = "read"


class ResourceMetadata(BaseModel):
    """Metadata common to all resources."""
    
    uuid: Optional[str] = None
    name: str
    description: Optional[str] = None
    labels: Dict[str, str] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_by: Optional[str] = None


class Resource(BaseModel):
    """Base class for all Salt Config resources."""
    
    resource_type: ResourceType
    metadata: ResourceMetadata
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def resource_type_value(self) -> str:
        """Get the resource type as a string value."""
        if isinstance(self.resource_type, ResourceType):
            return self.resource_type.value
        return str(self.resource_type)


class TargetExpression(BaseModel):
    """Target expression for matching minions."""
    
    target_type: str = Field(default="glob", description="Type: glob, grain, compound, nodegroup, etc.")
    target: str = Field(description="Target expression")
    
    
class TargetGroup(Resource):
    """Represents a Salt target group (collection of minions)."""
    
    resource_type: ResourceType = ResourceType.TARGET_GROUP
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def targets(self) -> List[TargetExpression]:
        """Get the list of target expressions."""
        raw_targets = self.spec.get("targets", [])
        return [TargetExpression(**t) if isinstance(t, dict) else t for t in raw_targets]
    
    @property
    def all_minions(self) -> bool:
        """Whether this target group matches all minions."""
        return self.spec.get("all_minions", False)


class JobType(str, Enum):
    """Types of Salt jobs."""
    
    STATE_APPLY = "state.apply"
    STATE_HIGHSTATE = "state.highstate"
    CMD_RUN = "cmd.run"
    SALT_RUNNER = "salt.runner"
    CUSTOM = "custom"


class Job(Resource):
    """Represents a Salt job definition."""
    
    resource_type: ResourceType = ResourceType.JOB
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def job_type(self) -> str:
        return self.spec.get("job_type", JobType.STATE_APPLY)
    
    @property
    def function(self) -> str:
        return self.spec.get("function", "state.apply")
    
    @property
    def arguments(self) -> List[str]:
        return self.spec.get("arguments", [])
    
    @property
    def kwargs(self) -> Dict[str, Any]:
        return self.spec.get("kwargs", {})
    
    @property
    def target_group(self) -> Optional[str]:
        return self.spec.get("target_group")


class ScheduleInterval(BaseModel):
    """Schedule interval configuration."""
    
    frequency: str = Field(description="Frequency: once, hourly, daily, weekly, monthly, cron")
    interval: Optional[int] = None
    cron_expression: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class Schedule(Resource):
    """Represents a Salt schedule definition."""
    
    resource_type: ResourceType = ResourceType.SCHEDULE
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def job(self) -> Optional[str]:
        return self.spec.get("job")
    
    @property
    def enabled(self) -> bool:
        return self.spec.get("enabled", True)
    
    @property
    def interval(self) -> Optional[ScheduleInterval]:
        interval_data = self.spec.get("interval")
        if interval_data:
            return ScheduleInterval(**interval_data)
        return None


class Pillar(Resource):
    """Represents Salt pillar data."""
    
    resource_type: ResourceType = ResourceType.PILLAR
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def environment(self) -> str:
        return self.spec.get("environment", "base")
    
    @property
    def data(self) -> Dict[str, Any]:
        return self.spec.get("data", {})
    
    @property
    def target_group(self) -> Optional[str]:
        return self.spec.get("target_group")


class StateFile(Resource):
    """Represents a Salt state file."""
    
    resource_type: ResourceType = ResourceType.STATE_FILE
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def environment(self) -> str:
        return self.spec.get("environment", "base")
    
    @property
    def path(self) -> str:
        return self.spec.get("path", "")
    
    @property
    def contents(self) -> str:
        return self.spec.get("contents", "")
    
    @property
    def content_type(self) -> str:
        return self.spec.get("content_type", "text/x-yaml")


class Minion(Resource):
    """Represents a Salt minion."""
    
    resource_type: ResourceType = ResourceType.MINION
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def minion_id(self) -> str:
        return self.spec.get("minion_id", self.metadata.name)
    
    @property
    def master(self) -> Optional[str]:
        return self.spec.get("master")
    
    @property
    def grains(self) -> Dict[str, Any]:
        return self.spec.get("grains", {})
    
    @property
    def key_state(self) -> str:
        return self.spec.get("key_state", "unknown")


class MinionState(Resource):
    """
    Represents expected minion configuration state.
    
    This is used for drift detection - defining what state should be applied
    to minions and detecting when they don't match.
    
    Example YAML (using target pattern):
        resource_type: minion_state
        metadata:
          name: ntp-compliance
        spec:
          state_file: /ntp-config.sls
          target: "*"
          target_type: glob
          environment: vcfsecops
    
    Example YAML (using target group name):
        resource_type: minion_state
        metadata:
          name: ntp-ops
        spec:
          state_file: /ntp-config.sls
          target_group: ops
          environment: vcfsecops
    """
    
    resource_type: ResourceType = ResourceType.MINION_STATE
    spec: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def state_file(self) -> str:
        """State file path on RaaS file server."""
        return self.spec.get("state_file", "")
    
    @property
    def state_files(self) -> List[str]:
        """Multiple state files to apply (if specified)."""
        files = self.spec.get("state_files", [])
        if not files and self.state_file:
            files = [self.state_file]
        return files
    
    @property
    def target_group(self) -> Optional[str]:
        """Target group name from RaaS (resolved at runtime)."""
        return self.spec.get("target_group")
    
    @property
    def target(self) -> str:
        """Target minion pattern (used if target_group not specified)."""
        return self.spec.get("target", "*")
    
    @property
    def target_type(self) -> str:
        """Target type: glob, grain, compound, list, etc."""
        return self.spec.get("target_type", "glob")
    
    @property
    def environment(self) -> str:
        """Salt environment."""
        return self.spec.get("environment", "base")
    
    @property
    def pillar(self) -> Dict[str, Any]:
        """Pillar data to pass when running the state."""
        return self.spec.get("pillar", {})
    
    @property
    def test_mode(self) -> bool:
        """Whether to run in test mode by default for drift detection."""
        return self.spec.get("test_mode", True)


class ResourceReference(BaseModel):
    """Reference to another resource."""
    
    resource_type: ResourceType
    name: str
    uuid: Optional[str] = None
    
    def __str__(self) -> str:
        return f"{self.resource_type.value}.{self.name}"


def resource_factory(resource_type: ResourceType, **kwargs) -> Resource:
    """Factory function to create appropriate resource type."""
    
    resource_classes = {
        ResourceType.TARGET_GROUP: TargetGroup,
        ResourceType.JOB: Job,
        ResourceType.SCHEDULE: Schedule,
        ResourceType.PILLAR: Pillar,
        ResourceType.STATE_FILE: StateFile,
        ResourceType.MINION: Minion,
        ResourceType.MINION_STATE: MinionState,
    }
    
    resource_class = resource_classes.get(resource_type, Resource)
    return resource_class(resource_type=resource_type, **kwargs)
