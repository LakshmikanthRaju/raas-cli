"""
Handler for Salt state file resources.
"""

from typing import Any, Dict, List, Optional

from salt_config_cli.api.client import AriaConfigClient
from salt_config_cli.api.exceptions import APIError
from salt_config_cli.core.models import ResourceType
from salt_config_cli.handlers.base import BaseResourceHandler


class StateFileHandler(BaseResourceHandler):
    """
    Handler for managing Salt state files in Aria Automation Config.
    
    State files contain Salt state definitions (SLS files) that define
    the desired configuration state for minions.
    """
    
    resource_type = ResourceType.STATE_FILE
    
    def create(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create or update a state file."""
        path = spec.get("path", name)
        contents = spec.get("contents", "")
        environment = spec.get("environment", "base")
        content_type = spec.get("content_type", "text/x-yaml")
        
        # Ensure path has correct extension
        if not path.endswith(".sls"):
            path = f"{path}.sls"
        
        response = client.call(
            "fs", "save_file",
            path=path,
            contents=contents,
            saltenv=environment,
            content_type=content_type,
        )
        
        if response.error:
            raise APIError(
                f"Failed to create state file: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def read(
        self, 
        client: AriaConfigClient, 
        identifier: str
    ) -> Optional[Dict[str, Any]]:
        """Read a state file by path."""
        path = identifier
        if not path.endswith(".sls"):
            path = f"{path}.sls"
        
        response = client.call("fs", "get_file", path=path)
        
        if response.error:
            if response.error.get("code") == 404:
                return None
            raise APIError(
                f"Failed to read state file: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def update(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing state file."""
        return self.create(client, name, spec)
    
    def delete(
        self, 
        client: AriaConfigClient, 
        name: str
    ) -> None:
        """Delete a state file."""
        path = name
        if not path.endswith(".sls"):
            path = f"{path}.sls"
        
        response = client.call("fs", "delete_file", path=path)
        
        if response.error:
            raise APIError(
                f"Failed to delete state file: {response.error.get('message')}",
                code=response.error.get("code")
            )
    
    def list(
        self, 
        client: AriaConfigClient,
        environment: str = "base"
    ) -> List[Dict[str, Any]]:
        """List all state files in an environment."""
        response = client.call(
            "fs", "get_files",
            saltenv=environment,
            path="",
            file_type="sls"
        )
        
        if response.error:
            raise APIError(
                f"Failed to list state files: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret or []
    
    def apply(
        self,
        client: AriaConfigClient,
        state_name: str,
        target: str = "*",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Apply a state to targets.
        
        Args:
            client: API client
            state_name: Name of the state to apply
            target: Target minions
            **kwargs: Additional state.apply options
        
        Returns:
            State apply result
        """
        response = client.call(
            "job", "run_job",
            tgt=target,
            fun="state.apply",
            arg=[state_name],
            kwarg=kwargs
        )
        
        if response.error:
            raise APIError(
                f"Failed to apply state: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
