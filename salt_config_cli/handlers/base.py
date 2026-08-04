"""
Base resource handler class.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from salt_config_cli.api.client import AriaConfigClient
from salt_config_cli.core.models import ResourceType


class BaseResourceHandler(ABC):
    """
    Abstract base class for resource handlers.
    
    Each handler implements CRUD operations for a specific resource type
    in VMware Aria Automation Config.
    """
    
    resource_type: ResourceType
    
    @abstractmethod
    def create(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new resource.
        
        Args:
            client: API client
            name: Resource name
            spec: Resource specification
        
        Returns:
            Created resource data including UUID
        """
        pass
    
    @abstractmethod
    def read(
        self, 
        client: AriaConfigClient, 
        identifier: str
    ) -> Optional[Dict[str, Any]]:
        """
        Read a resource from the server.
        
        Args:
            client: API client
            identifier: Resource name or UUID
        
        Returns:
            Resource data or None if not found
        """
        pass
    
    @abstractmethod
    def update(
        self, 
        client: AriaConfigClient, 
        name: str, 
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing resource.
        
        Args:
            client: API client
            name: Resource name
            spec: Updated resource specification
        
        Returns:
            Updated resource data
        """
        pass
    
    @abstractmethod
    def delete(
        self, 
        client: AriaConfigClient, 
        name: str
    ) -> None:
        """
        Delete a resource.
        
        Args:
            client: API client
            name: Resource name
        """
        pass
    
    @abstractmethod
    def list(
        self, 
        client: AriaConfigClient
    ) -> List[Dict[str, Any]]:
        """
        List all resources of this type.
        
        Args:
            client: API client
        
        Returns:
            List of resource data
        """
        pass
    
    def diff(
        self, 
        current: Dict[str, Any], 
        desired: Dict[str, Any]
    ) -> Dict[str, tuple]:
        """
        Compute differences between current and desired state.
        
        Args:
            current: Current resource state
            desired: Desired resource state
        
        Returns:
            Dict of changed attributes: {attr: (old_value, new_value)}
        """
        changes = {}
        all_keys = set(current.keys()) | set(desired.keys())
        
        # Ignore metadata fields that shouldn't trigger updates
        ignore_keys = {"uuid", "created_at", "modified_at", "created_by", "modified_by"}
        
        for key in all_keys - ignore_keys:
            current_val = current.get(key)
            desired_val = desired.get(key)
            if current_val != desired_val:
                changes[key] = (current_val, desired_val)
        
        return changes
    
    def normalize_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize specification for comparison.
        
        Override in subclasses to handle type-specific normalization.
        """
        return spec
