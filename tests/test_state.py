"""
Tests for state management.
"""

import json
import tempfile
from pathlib import Path

import pytest

from salt_config_cli.core.models import ResourceType
from salt_config_cli.core.state import StateManager, StateFile, ResourceState


class TestResourceState:
    """Tests for ResourceState."""
    
    def test_create_resource_state(self):
        state = ResourceState(
            resource_type=ResourceType.TARGET_GROUP,
            name="web-servers",
            uuid="abc-123",
            attributes={"targets": []}
        )
        assert state.resource_type == ResourceType.TARGET_GROUP
        assert state.name == "web-servers"
        assert state.uuid == "abc-123"
    
    def test_resource_address(self):
        state = ResourceState(
            resource_type=ResourceType.JOB,
            name="deploy-app"
        )
        assert state.resource_address == "job.deploy-app"
    
    def test_compute_hash(self):
        state = ResourceState(
            resource_type=ResourceType.PILLAR,
            name="config",
            attributes={"key": "value"}
        )
        hash1 = state.compute_hash()
        assert len(hash1) == 16
        
        # Same attributes should produce same hash
        state.attributes = {"key": "value"}
        hash2 = state.compute_hash()
        assert hash1 == hash2
        
        # Different attributes should produce different hash
        state.attributes = {"key": "different"}
        hash3 = state.compute_hash()
        assert hash1 != hash3
    
    def test_has_drift(self):
        state = ResourceState(
            resource_type=ResourceType.TARGET_GROUP,
            name="test",
            config_hash="abc123",
            remote_hash="abc123"
        )
        assert state.has_drift() is False
        
        state.remote_hash = "different"
        assert state.has_drift() is True


class TestStateFile:
    """Tests for StateFile."""
    
    def test_create_empty_state(self):
        state = StateFile()
        assert state.version == 1
        assert state.serial == 0
        assert state.resources == {}
    
    def test_get_set_resource(self):
        state = StateFile()
        
        resource = ResourceState(
            resource_type=ResourceType.TARGET_GROUP,
            name="web-servers",
            attributes={"targets": []}
        )
        
        state.set_resource(resource)
        assert state.serial == 1
        
        retrieved = state.get_resource(ResourceType.TARGET_GROUP, "web-servers")
        assert retrieved is not None
        assert retrieved.name == "web-servers"
    
    def test_remove_resource(self):
        state = StateFile()
        
        resource = ResourceState(
            resource_type=ResourceType.JOB,
            name="test-job"
        )
        state.set_resource(resource)
        
        removed = state.remove_resource(ResourceType.JOB, "test-job")
        assert removed is not None
        assert removed.name == "test-job"
        
        # Should not exist anymore
        assert state.get_resource(ResourceType.JOB, "test-job") is None
    
    def test_list_resources(self):
        state = StateFile()
        
        state.set_resource(ResourceState(
            resource_type=ResourceType.TARGET_GROUP,
            name="tg1"
        ))
        state.set_resource(ResourceState(
            resource_type=ResourceType.TARGET_GROUP,
            name="tg2"
        ))
        state.set_resource(ResourceState(
            resource_type=ResourceType.JOB,
            name="job1"
        ))
        
        all_resources = state.list_resources()
        assert len(all_resources) == 3
        
        target_groups = state.list_resources(ResourceType.TARGET_GROUP)
        assert len(target_groups) == 2
        
        jobs = state.list_resources(ResourceType.JOB)
        assert len(jobs) == 1


class TestStateManager:
    """Tests for StateManager."""
    
    def test_create_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            assert manager.backend == "local"
            assert manager._state is None
    
    def test_load_empty_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            state = manager.load()
            assert state is not None
            assert state.version == 1
            assert len(state.resources) == 0
    
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            # Add resource
            resource = ResourceState(
                resource_type=ResourceType.TARGET_GROUP,
                name="test-group",
                attributes={"targets": ["web-*"]}
            )
            manager.set_resource(resource)
            manager.save()
            
            # Load in new manager
            manager2 = StateManager(state_path=str(state_path))
            loaded = manager2.get_resource(ResourceType.TARGET_GROUP, "test-group")
            
            assert loaded is not None
            assert loaded.name == "test-group"
            assert loaded.attributes == {"targets": ["web-*"]}
    
    def test_lock_unlock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            # First lock should succeed
            assert manager.lock() is True
            
            # Second lock should fail
            manager2 = StateManager(state_path=str(state_path))
            assert manager2.lock() is False
            
            # After unlock, should succeed
            manager.unlock()
            assert manager2.lock() is True
            manager2.unlock()
