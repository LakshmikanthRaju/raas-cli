"""
Handler for Salt target group resources.
"""

from typing import Any, Dict, List, Optional

from salt_config_cli.api.client import AriaConfigClient
from salt_config_cli.api.exceptions import APIError, NotFoundError
from salt_config_cli.core.models import ResourceType
from salt_config_cli.handlers.base import BaseResourceHandler


class TargetGroupHandler(BaseResourceHandler):
    """
    Handler for managing Salt target groups in Aria Automation Config.
    
    Target groups define collections of minions that can be targeted
    for job execution.
    """
    
    resource_type = ResourceType.TARGET_GROUP
    
    def create(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new target group."""
        targets = spec.get("targets", [])
        description = spec.get("description", "")
        all_minions = spec.get("all_minions", False)
        
        response = client.call(
            "tgt", "save_target_group",
            name=name,
            tgt=targets,
            desc=description,
            all_minions=all_minions
        )
        
        if response.error:
            raise APIError(
                f"Failed to create target group: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def read(
        self, 
        client: AriaConfigClient, 
        identifier: str
    ) -> Optional[Dict[str, Any]]:
        """Read a target group by name or UUID."""
        response = client.call("tgt", "get_target_group", name=identifier)
        
        if response.error:
            if response.error.get("code") == 404:
                return None
            raise APIError(
                f"Failed to read target group: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def update(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing target group."""
        # In Aria Config, updates are done via save with the same name
        return self.create(client, name, spec)
    
    def delete(
        self, 
        client: AriaConfigClient, 
        name: str
    ) -> None:
        """Delete a target group."""
        response = client.call("tgt", "delete_target_group", name=name)
        
        if response.error:
            raise APIError(
                f"Failed to delete target group: {response.error.get('message')}",
                code=response.error.get("code")
            )
    
    def list(
        self, 
        client: AriaConfigClient
    ) -> List[Dict[str, Any]]:
        """List all target groups."""
        response = client.call("tgt", "get_target_group")
        
        if response.error:
            raise APIError(
                f"Failed to list target groups: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret or []
    
    def normalize_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize target group specification."""
        normalized = dict(spec)
        
        # Ensure targets is a list
        if "targets" not in normalized:
            normalized["targets"] = []
        
        # Normalize target format
        targets = []
        for target in normalized["targets"]:
            if isinstance(target, str):
                targets.append({"target_type": "glob", "target": target})
            elif isinstance(target, dict):
                targets.append(target)
        normalized["targets"] = targets
        
        return normalized
