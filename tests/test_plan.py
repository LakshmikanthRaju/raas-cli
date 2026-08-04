"""
Tests for plan execution.
"""

import tempfile
from pathlib import Path

import pytest

from salt_config_cli.core.models import ResourceType, ResourceMetadata, TargetGroup
from salt_config_cli.core.plan import Plan, ResourceChange, PlanExecutor
from salt_config_cli.core.state import StateManager, ResourceState


class TestResourceChange:
    """Tests for ResourceChange."""
    
    def test_create_change(self):
        from salt_config_cli.core.models import ChangeAction
        
        change = ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.TARGET_GROUP,
            name="web-servers",
            after={"targets": ["web-*"]}
        )
        
        assert change.action == ChangeAction.CREATE
        assert change.resource_address == "target_group.web-servers"
    
    def test_change_summary(self):
        from salt_config_cli.core.models import ChangeAction
        
        create = ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.JOB,
            name="deploy"
        )
        assert "+" in create.get_change_summary()
        
        update = ResourceChange(
            action=ChangeAction.UPDATE,
            resource_type=ResourceType.JOB,
            name="deploy"
        )
        assert "~" in update.get_change_summary()
        
        delete = ResourceChange(
            action=ChangeAction.DELETE,
            resource_type=ResourceType.JOB,
            name="deploy"
        )
        assert "-" in delete.get_change_summary()


class TestPlan:
    """Tests for Plan."""
    
    def test_empty_plan(self):
        plan = Plan()
        assert plan.has_changes is False
        assert plan.is_valid is True
        assert plan.to_create == 0
        assert plan.to_update == 0
        assert plan.to_delete == 0
    
    def test_add_changes(self):
        from salt_config_cli.core.models import ChangeAction
        
        plan = Plan()
        
        plan.add_change(ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.TARGET_GROUP,
            name="tg1"
        ))
        plan.add_change(ResourceChange(
            action=ChangeAction.UPDATE,
            resource_type=ResourceType.TARGET_GROUP,
            name="tg2"
        ))
        plan.add_change(ResourceChange(
            action=ChangeAction.DELETE,
            resource_type=ResourceType.JOB,
            name="job1"
        ))
        
        assert plan.has_changes is True
        assert plan.to_create == 1
        assert plan.to_update == 1
        assert plan.to_delete == 1
        assert len(plan.changes) == 3
    
    def test_plan_summary(self):
        from salt_config_cli.core.models import ChangeAction
        
        plan = Plan()
        plan.add_change(ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.TARGET_GROUP,
            name="tg1"
        ))
        plan.add_change(ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.TARGET_GROUP,
            name="tg2"
        ))
        
        summary = plan.get_summary()
        assert "2 to create" in summary
    
    def test_ordered_changes(self):
        from salt_config_cli.core.models import ChangeAction
        
        plan = Plan()
        
        # Add changes with dependencies
        plan.add_change(ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.JOB,
            name="job1",
            depends_on=["target_group.tg1"]
        ))
        plan.add_change(ResourceChange(
            action=ChangeAction.CREATE,
            resource_type=ResourceType.TARGET_GROUP,
            name="tg1"
        ))
        
        ordered = plan.get_ordered_changes()
        
        # Target group should come before job
        tg_idx = next(i for i, c in enumerate(ordered) if c.name == "tg1")
        job_idx = next(i for i, c in enumerate(ordered) if c.name == "job1")
        assert tg_idx < job_idx


class TestPlanExecutor:
    """Tests for PlanExecutor."""
    
    def test_create_executor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            executor = PlanExecutor(
                state_manager=manager,
                config_dir=tmpdir
            )
            
            assert executor.state_manager is manager
    
    def test_plan_create_resources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = Path(tmpdir) / "resources.yaml"
            config_path.write_text("""
resource_type: target_group
metadata:
  name: web-servers
  description: Web servers
spec:
  targets:
    - target_type: glob
      target: "web-*"
""")
            
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            executor = PlanExecutor(
                state_manager=manager,
                config_dir=tmpdir
            )
            
            plan = executor.plan()
            
            assert plan.to_create == 1
            assert plan.changes[0].name == "web-servers"
    
    def test_plan_no_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_path = Path(tmpdir) / "resources.yaml"
            config_path.write_text("""
resource_type: target_group
metadata:
  name: existing-group
spec:
  targets: []
""")
            
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            # Pre-populate state
            manager.set_resource(ResourceState(
                resource_type=ResourceType.TARGET_GROUP,
                name="existing-group",
                attributes={"targets": []}
            ))
            
            executor = PlanExecutor(
                state_manager=manager,
                config_dir=tmpdir
            )
            
            plan = executor.plan()
            
            # Should have one unchanged resource
            assert plan.to_create == 0
            assert plan.unchanged == 1
    
    def test_plan_destroy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / ".scc" / "terraform.tfstate"
            manager = StateManager(state_path=str(state_path))
            
            # Add resources to state
            manager.set_resource(ResourceState(
                resource_type=ResourceType.TARGET_GROUP,
                name="group1"
            ))
            manager.set_resource(ResourceState(
                resource_type=ResourceType.JOB,
                name="job1"
            ))
            
            executor = PlanExecutor(
                state_manager=manager,
                config_dir=tmpdir
            )
            
            plan = executor.plan(destroy=True)
            
            assert plan.to_delete == 2
