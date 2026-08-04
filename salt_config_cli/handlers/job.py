"""
Handler for Salt job resources.
"""

from typing import Any, Dict, List, Optional

from salt_config_cli.api.client import AriaConfigClient
from salt_config_cli.api.exceptions import APIError
from salt_config_cli.core.models import ResourceType
from salt_config_cli.handlers.base import BaseResourceHandler


class JobHandler(BaseResourceHandler):
    """
    Handler for managing Salt jobs in Aria Automation Config.
    
    Jobs define Salt commands that can be executed against target groups.
    """
    
    resource_type = ResourceType.JOB
    
    def create(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a new job definition."""
        # Build arg dict for API: {"arg": [...], "kwarg": {...}}
        arg_dict = {}
        if spec.get("arguments"):
            arg_dict["arg"] = spec.get("arguments", [])
        if spec.get("kwargs"):
            arg_dict["kwarg"] = spec.get("kwargs", {})
        
        response = client.call(
            "job", "save_job",
            name=name,
            fun=spec.get("function", "state.apply"),
            cmd=spec.get("cmd", "local"),
            tgt_uuid=spec.get("target_group_uuid"),
            arg=arg_dict,
            desc=spec.get("description", ""),
        )
        
        if response.error:
            raise APIError(
                f"Failed to create job: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def read(
        self, 
        client: AriaConfigClient, 
        identifier: str
    ) -> Optional[Dict[str, Any]]:
        """Read a job by name or UUID."""
        response = client.call("job", "get_job", name=identifier)
        
        if response.error:
            if response.error.get("code") == 404:
                return None
            raise APIError(
                f"Failed to read job: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
    
    def update(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing job."""
        return self.create(client, name, spec)
    
    def delete(
        self, 
        client: AriaConfigClient, 
        name: str
    ) -> None:
        """Delete a job."""
        response = client.call("job", "delete_job", name=name)
        
        if response.error:
            raise APIError(
                f"Failed to delete job: {response.error.get('message')}",
                code=response.error.get("code")
            )
    
    def list(
        self, 
        client: AriaConfigClient
    ) -> List[Dict[str, Any]]:
        """List all jobs."""
        response = client.call("job", "get_jobs")
        
        if response.error:
            raise APIError(
                f"Failed to list jobs: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret or []
    
    def run(
        self,
        client: AriaConfigClient,
        job_uuid: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a job by UUID.
        
        Args:
            client: API client
            job_uuid: Job UUID
            **kwargs: Additional run options
        
        Returns:
            Job execution result (JID)
        """
        run_kwargs = {"job_uuid": job_uuid}
        run_kwargs.update(kwargs)
        
        response = client.call("cmd", "route_cmd", **run_kwargs)
        
        if response.error:
            raise APIError(
                f"Failed to run job: {response.error.get('message')}",
                code=response.error.get("code")
            )
        
        return response.ret
