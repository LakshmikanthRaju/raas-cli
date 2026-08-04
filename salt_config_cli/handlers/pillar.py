"""
Handler for Salt pillar resources.
"""

from typing import Any, Dict, List, Optional

from salt_config_cli.api.client import AriaConfigClient
from salt_config_cli.api.exceptions import APIError
from salt_config_cli.core.models import ResourceType
from salt_config_cli.handlers.base import BaseResourceHandler


class PillarHandler(BaseResourceHandler):
    """
    Handler for managing Salt pillar data in Aria Automation Config.
    
    Pillars contain configuration data that can be securely distributed
    to minions.
    """
    
    resource_type = ResourceType.PILLAR
    
    def create(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new pillar."""
        pillar_data = spec.get("data", {})
        
        response = client.call(
            "pillar", "save_pillar",
            name=name,
            pillar=pillar_data,
            pillar_type="static",
            desc=spec.get("description", ""),
        )
        
        if response.error:
            raise APIError(
                f"Failed to create pillar: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def read(
        self, 
        client: AriaConfigClient, 
        identifier: str
    ) -> Optional[Dict[str, Any]]:
        """Read a pillar by name or UUID."""
        response = client.call("pillar", "get_pillar", name=identifier)
        
        if response.error:
            if response.error.get("code") == 404:
                return None
            raise APIError(
                f"Failed to read pillar: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def update(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing pillar."""
        return self.create(client, name, spec)
    
    def delete(
        self, 
        client: AriaConfigClient, 
        name: str
    ) -> None:
        """Delete a pillar."""
        response = client.call("pillar", "delete_pillar", name=name)
        
        if response.error:
            raise APIError(
                f"Failed to delete pillar: {response.error.get('message')}",
                code=response.error.get("code")
            )
    
    def list(
        self, 
        client: AriaConfigClient
    ) -> List[Dict[str, Any]]:
        """List all pillars."""
        response = client.call("pillar", "get_pillars")
        
        if response.error:
            raise APIError(
                f"Failed to list pillars: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret or []
    
    def refresh(
        self,
        client: AriaConfigClient,
        target: str = "*"
    ) -> Dict[str, Any]:
        """
        Refresh pillar data on minions.
        
        Args:
            client: API client
            target: Target minions
        
        Returns:
            Refresh result
        """
        response = client.call(
            "job", "run_job",
            tgt=target,
            fun="saltutil.refresh_pillar"
        )
        
        if response.error:
            raise APIError(
                f"Failed to refresh pillar: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
