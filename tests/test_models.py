"""
Tests for core data models.
"""

import pytest
from salt_config_cli.core.models import (
    Resource,
    ResourceType,
    ResourceMetadata,
    TargetGroup,
    Job,
    Pillar,
    StateFile,
    resource_factory,
)


class TestResourceMetadata:
    """Tests for ResourceMetadata."""
    
    def test_create_metadata(self):
        metadata = ResourceMetadata(
            name="test-resource",
            description="A test resource"
        )
        assert metadata.name == "test-resource"
        assert metadata.description == "A test resource"
        assert metadata.uuid is None
        assert metadata.labels == {}
    
    def test_metadata_with_labels(self):
        metadata = ResourceMetadata(
            name="test-resource",
            labels={"env": "prod", "tier": "frontend"}
        )
        assert metadata.labels == {"env": "prod", "tier": "frontend"}


class TestTargetGroup:
    """Tests for TargetGroup resource."""
    
    def test_create_target_group(self):
        tg = TargetGroup(
            metadata=ResourceMetadata(name="web-servers"),
            spec={
                "targets": [
                    {"target_type": "glob", "target": "web-*"}
                ]
            }
        )
        assert tg.resource_type == ResourceType.TARGET_GROUP
        assert tg.metadata.name == "web-servers"
    
    def test_target_group_targets(self):
        tg = TargetGroup(
            metadata=ResourceMetadata(name="test"),
            spec={
                "targets": [
                    {"target_type": "glob", "target": "web-*"},
                    {"target_type": "grain", "target": "roles:db"}
                ]
            }
        )
        targets = tg.targets
        assert len(targets) == 2
        assert targets[0].target_type == "glob"
        assert targets[0].target == "web-*"
    
    def test_target_group_all_minions(self):
        tg = TargetGroup(
            metadata=ResourceMetadata(name="all"),
            spec={"all_minions": True}
        )
        assert tg.all_minions is True


class TestJob:
    """Tests for Job resource."""
    
    def test_create_job(self):
        job = Job(
            metadata=ResourceMetadata(name="deploy-app"),
            spec={
                "function": "state.apply",
                "arguments": ["myapp"]
            }
        )
        assert job.resource_type == ResourceType.JOB
        assert job.function == "state.apply"
        assert job.arguments == ["myapp"]
    
    def test_job_defaults(self):
        job = Job(
            metadata=ResourceMetadata(name="test"),
            spec={}
        )
        assert job.function == "state.apply"
        assert job.arguments == []
        assert job.kwargs == {}


class TestPillar:
    """Tests for Pillar resource."""
    
    def test_create_pillar(self):
        pillar = Pillar(
            metadata=ResourceMetadata(name="app-config"),
            spec={
                "environment": "base",
                "data": {"app": {"port": 8080}}
            }
        )
        assert pillar.resource_type == ResourceType.PILLAR
        assert pillar.environment == "base"
        assert pillar.data == {"app": {"port": 8080}}
    
    def test_pillar_defaults(self):
        pillar = Pillar(
            metadata=ResourceMetadata(name="test"),
            spec={}
        )
        assert pillar.environment == "base"
        assert pillar.data == {}


class TestStateFile:
    """Tests for StateFile resource."""
    
    def test_create_state_file(self):
        sf = StateFile(
            metadata=ResourceMetadata(name="nginx"),
            spec={
                "path": "nginx/init.sls",
                "contents": "nginx:\n  pkg.installed: []"
            }
        )
        assert sf.resource_type == ResourceType.STATE_FILE
        assert sf.path == "nginx/init.sls"
        assert "pkg.installed" in sf.contents


class TestResourceFactory:
    """Tests for resource_factory function."""
    
    def test_create_target_group(self):
        resource = resource_factory(
            ResourceType.TARGET_GROUP,
            metadata=ResourceMetadata(name="test"),
            spec={}
        )
        assert isinstance(resource, TargetGroup)
    
    def test_create_job(self):
        resource = resource_factory(
            ResourceType.JOB,
            metadata=ResourceMetadata(name="test"),
            spec={}
        )
        assert isinstance(resource, Job)
    
    def test_create_pillar(self):
        resource = resource_factory(
            ResourceType.PILLAR,
            metadata=ResourceMetadata(name="test"),
            spec={}
        )
        assert isinstance(resource, Pillar)
