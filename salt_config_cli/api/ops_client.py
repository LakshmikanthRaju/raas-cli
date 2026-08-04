"""
HTTP client for VMware VCF Operations (Ops) API.

Provides resource information from VCF Operations that can be mapped to 
Salt minions managed by Aria Automation Config (RaaS).

Authentication is done via token acquisition:
    POST /suite-api/api/auth/token/acquire
    
Resources are queried via:
    GET /suite-api/api/resources
    POST /suite-api/api/resources/query
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from salt_config_cli.api.exceptions import (
    APIError,
    AuthenticationError,
    ConnectionError,
    NotFoundError,
    ServerError,
    TimeoutError,
)

log = logging.getLogger(__name__)


@dataclass
class OpsResource:
    """Represents a resource from VCF Operations."""
    
    identifier: str
    name: str
    adapter_kind: str
    resource_kind: str
    description: str = ""
    health: str = "UNKNOWN"
    version: str = ""
    build: str = ""
    resource_identifiers: Dict[str, str] = field(default_factory=dict)
    properties: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpsResource":
        """Create OpsResource from API response dictionary."""
        resource_key = data.get("resourceKey", {})
        
        identifiers = {}
        for ri in resource_key.get("resourceIdentifiers", []):
            name = ri.get("identifierType", {}).get("name", ri.get("name", ""))
            value = ri.get("value", "")
            if name and value:
                identifiers[name] = value
        
        health = "UNKNOWN"
        health_value = data.get("resourceHealth")
        if health_value:
            health = health_value
        elif data.get("resourceStatusStates"):
            for state in data["resourceStatusStates"]:
                if state.get("resourceState") == "STARTED":
                    health = "GREEN"
                    break
        
        properties = {}
        for prop in data.get("resourceProperties", data.get("properties", [])):
            prop_name = prop.get("name", prop.get("statKey", ""))
            prop_value = prop.get("value", prop.get("values", [""])[-1] if prop.get("values") else "")
            if prop_name:
                properties[prop_name] = str(prop_value) if prop_value else ""
        
        version = (
            properties.get("summary|version", "") or
            properties.get("config|product|version", "") or
            properties.get("System|product_version", "") or
            properties.get("version", "") or
            identifiers.get("VMEntityVersion", "")
        )
        
        build = (
            properties.get("summary|build", "") or
            properties.get("config|product|build", "") or
            properties.get("System|product_build", "") or
            properties.get("build", "") or
            properties.get("buildNumber", "") or
            identifiers.get("VMEntityBuild", "")
        )
        
        return cls(
            identifier=data.get("identifier", ""),
            name=resource_key.get("name", ""),
            adapter_kind=resource_key.get("adapterKindKey", ""),
            resource_kind=resource_key.get("resourceKindKey", ""),
            description=data.get("description", ""),
            health=health,
            version=version,
            build=build,
            resource_identifiers=identifiers,
            properties=properties,
        )
    
    def get_version_string(self) -> str:
        """Get formatted version string with build number."""
        if self.version and self.build:
            return f"{self.version} ({self.build})"
        return self.version or self.build or ""


class OpsClient:
    """
    Client for VMware VCF Operations API.
    
    Provides access to resource information that can be correlated with
    Salt minions in Aria Automation Config.
    
    Example:
        >>> client = OpsClient.connect(
        ...     server="https://vcfops.example.com",
        ...     username="admin",
        ...     password="password",
        ...     ssl_verify=False
        ... )
        >>> resources = client.get_resources()
        >>> for r in resources:
        ...     print(f"{r.identifier}: {r.name}")
    """
    
    API_BASE = "/suite-api"
    TOKEN_ENDPOINT = "/api/auth/token/acquire"
    RESOURCES_ENDPOINT = "/api/resources"
    RESOURCES_QUERY_ENDPOINT = "/api/resources/query"
    
    def __init__(
        self,
        server: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 60,
        ssl_verify: bool = True,
    ):
        """
        Initialize the Ops client.
        
        Args:
            server: URL of the VCF Operations server
            username: Username for authentication
            password: Password for authentication
            timeout: Request timeout in seconds
            ssl_verify: Whether to verify SSL certificates
        """
        self.server = server.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.ssl_verify = ssl_verify
        
        self._token: Optional[str] = None
        self._authenticated = False
        
        self._client = httpx.Client(
            timeout=timeout,
            verify=ssl_verify,
            follow_redirects=True,
        )
    
    @classmethod
    def connect(
        cls,
        server: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        ssl_verify: bool = True,
        **kwargs
    ) -> "OpsClient":
        """
        Create and connect a client instance.
        
        Args:
            server: VCF Operations server URL
            username: Username for authentication
            password: Password for authentication
            ssl_verify: Whether to validate SSL certificates
            **kwargs: Additional arguments passed to __init__
        
        Returns:
            Connected OpsClient instance
        """
        client = cls(
            server=server,
            username=username,
            password=password,
            ssl_verify=ssl_verify,
            **kwargs
        )
        client.authenticate()
        return client
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "OpsClient":
        """Create client from config dictionary."""
        return cls.connect(**config)
    
    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()
    
    def __enter__(self) -> "OpsClient":
        return self
    
    def __exit__(self, *args) -> None:
        self.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        if self._token:
            headers["Authorization"] = f"OpsToken {self._token}"
        
        return headers
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle HTTP response and raise appropriate exceptions."""
        if response.status_code == 401:
            raise AuthenticationError(
                "Authentication failed - check username/password",
                code=401,
                detail=response.text
            )
        
        if response.status_code == 403:
            raise AuthenticationError(
                "Access forbidden - insufficient permissions",
                code=403,
                detail=response.text
            )
        
        if response.status_code == 404:
            raise NotFoundError(
                "Resource not found",
                code=404,
                detail=response.text
            )
        
        if response.status_code >= 500:
            raise ServerError(
                "Server error",
                code=response.status_code,
                detail=response.text
            )
        
        if response.status_code == 204:
            return {}
        
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw": response.text}
    
    def authenticate(self) -> None:
        """
        Authenticate with the VCF Operations server.
        
        Acquires a token via POST /suite-api/api/auth/token/acquire
        """
        if not self.username or not self.password:
            raise AuthenticationError("Username and password are required")
        
        url = f"{self.server}{self.API_BASE}{self.TOKEN_ENDPOINT}"
        payload = {
            "username": self.username,
            "password": self.password,
        }
        
        try:
            log.debug(f"Authenticating with Ops server: {self.server}")
            response = self._client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            
            if response.status_code != 200:
                self._handle_response(response)
            
            data = response.json()
            self._token = data.get("token")
            
            if not self._token:
                raise AuthenticationError(
                    "No token received from server",
                    detail=str(data)
                )
            
            self._authenticated = True
            log.info("Ops authentication successful")
            
        except httpx.TimeoutException:
            raise TimeoutError("Authentication request timed out")
        except httpx.RequestError as e:
            raise ConnectionError(f"Failed to connect to Ops server: {e}")
    
    def get_resources(
        self,
        page: int = 0,
        page_size: int = 1000,
        resource_kind: Optional[str] = None,
        adapter_kind: Optional[str] = None,
        name: Optional[List[str]] = None,
    ) -> List[OpsResource]:
        """
        Get resources from VCF Operations.
        
        Args:
            page: Page number (0-indexed)
            page_size: Number of resources per page
            resource_kind: Filter by resource kind (e.g., "VirtualMachine")
            adapter_kind: Filter by adapter kind (e.g., "VMWARE")
            name: Filter by resource names
        
        Returns:
            List of OpsResource objects
        """
        params = {
            "page": page,
            "pageSize": page_size,
        }
        
        if resource_kind:
            params["resourceKind"] = resource_kind
        if adapter_kind:
            params["adapterKind"] = adapter_kind
        if name:
            params["name"] = name
        
        url = f"{self.server}{self.API_BASE}{self.RESOURCES_ENDPOINT}"
        
        try:
            response = self._client.get(
                url,
                params=params,
                headers=self._get_headers(),
            )
            
            if response.status_code >= 400:
                self._handle_response(response)
            
            data = response.json()
            resource_list = data.get("resourceList", data.get("resources", []))
            
            return [OpsResource.from_dict(r) for r in resource_list]
            
        except httpx.TimeoutException:
            raise TimeoutError("Request timed out getting resources")
        except httpx.RequestError as e:
            raise ConnectionError(f"Request failed: {e}")
    
    def query_resources(
        self,
        resource_ids: Optional[List[str]] = None,
        names: Optional[List[str]] = None,
        resource_kind: Optional[List[str]] = None,
        adapter_kind: Optional[List[str]] = None,
        page: int = 0,
        page_size: int = 1000,
    ) -> List[OpsResource]:
        """
        Query resources using POST with ResourceQuery.
        
        Args:
            resource_ids: List of resource UUIDs to query
            names: List of resource names to query
            resource_kind: List of resource kinds to filter
            adapter_kind: List of adapter kinds to filter
            page: Page number
            page_size: Page size
        
        Returns:
            List of OpsResource objects
        """
        query = {}
        
        if resource_ids:
            query["resourceId"] = resource_ids
        if names:
            query["name"] = names
        if resource_kind:
            query["resourceKind"] = resource_kind
        if adapter_kind:
            query["adapterKind"] = adapter_kind
        
        url = f"{self.server}{self.API_BASE}{self.RESOURCES_QUERY_ENDPOINT}"
        params = {"page": page, "pageSize": page_size}
        
        try:
            response = self._client.post(
                url,
                json=query,
                params=params,
                headers=self._get_headers(),
            )
            
            if response.status_code >= 400:
                self._handle_response(response)
            
            data = response.json()
            resource_list = data.get("resourceList", data.get("resources", []))
            
            return [OpsResource.from_dict(r) for r in resource_list]
            
        except httpx.TimeoutException:
            raise TimeoutError("Request timed out querying resources")
        except httpx.RequestError as e:
            raise ConnectionError(f"Request failed: {e}")
    
    def get_resource(self, resource_id: str) -> Optional[OpsResource]:
        """
        Get a single resource by ID.
        
        Args:
            resource_id: The resource UUID
        
        Returns:
            OpsResource if found, None otherwise
        """
        url = f"{self.server}{self.API_BASE}{self.RESOURCES_ENDPOINT}/{resource_id}"
        
        try:
            response = self._client.get(
                url,
                headers=self._get_headers(),
            )
            
            if response.status_code == 404:
                return None
            
            if response.status_code >= 400:
                self._handle_response(response)
            
            data = response.json()
            return OpsResource.from_dict(data)
            
        except httpx.TimeoutException:
            raise TimeoutError("Request timed out getting resource")
        except httpx.RequestError as e:
            raise ConnectionError(f"Request failed: {e}")
    
    def get_resource_properties(
        self,
        resource_id: str,
    ) -> Dict[str, str]:
        """
        Get properties for a specific resource.
        
        Args:
            resource_id: The resource UUID
        
        Returns:
            Dictionary of property name to value
        """
        url = f"{self.server}{self.API_BASE}{self.RESOURCES_ENDPOINT}/{resource_id}/properties"
        
        try:
            response = self._client.get(
                url,
                headers=self._get_headers(),
            )
            
            if response.status_code == 404:
                return {}
            
            if response.status_code >= 400:
                self._handle_response(response)
            
            data = response.json()
            properties = {}
            
            for prop in data.get("property", data.get("resourceProperties", [])):
                prop_name = prop.get("name", prop.get("statKey", ""))
                values = prop.get("values", [])
                prop_value = values[-1] if values else prop.get("value", "")
                if prop_name:
                    properties[prop_name] = str(prop_value) if prop_value else ""
            
            return properties
            
        except httpx.TimeoutException:
            raise TimeoutError("Request timed out getting properties")
        except httpx.RequestError as e:
            raise ConnectionError(f"Request failed: {e}")
    
    def get_resources_with_properties(
        self,
        page: int = 0,
        page_size: int = 1000,
        resource_kind: Optional[str] = None,
        adapter_kind: Optional[str] = None,
        name: Optional[List[str]] = None,
        property_keys: Optional[List[str]] = None,
    ) -> List[OpsResource]:
        """
        Get resources with their properties from VCF Operations.
        
        Uses the properties/latest/query endpoint for efficient batch fetching.
        
        Args:
            page: Page number (0-indexed)
            page_size: Number of resources per page
            resource_kind: Filter by resource kind
            adapter_kind: Filter by adapter kind
            name: Filter by resource names
            property_keys: List of property keys to fetch (e.g., ["summary|version", "summary|build"])
        
        Returns:
            List of OpsResource objects with properties populated
        """
        resources = self.get_resources(
            page=page,
            page_size=page_size,
            resource_kind=resource_kind,
            adapter_kind=adapter_kind,
            name=name,
        )
        
        if not resources:
            return resources
        
        resource_ids = [r.identifier for r in resources]
        
        if property_keys is None:
            property_keys = [
                "summary|version",
                "summary|build", 
                "config|product|version",
                "config|product|build",
                "System|product_version",
                "System|product_build",
            ]
        
        url = f"{self.server}{self.API_BASE}/api/resources/properties/latest/query"
        
        query = {
            "resourceIds": resource_ids,
            "propertyKeys": property_keys,
        }
        
        try:
            response = self._client.post(
                url,
                json=query,
                headers=self._get_headers(),
            )
            
            if response.status_code >= 400:
                log.warning(f"Failed to fetch properties: {response.status_code}")
                return resources
            
            data = response.json()
            
            resource_props_map = {}
            for item in data.get("values", []):
                res_id = item.get("resourceId", "")
                props = {}
                for prop in item.get("property-contents", {}).get("property-content", []):
                    stat_key = prop.get("statKey", "")
                    values = prop.get("values", [])
                    if stat_key and values:
                        props[stat_key] = str(values[-1])
                if res_id:
                    resource_props_map[res_id] = props
            
            for resource in resources:
                props = resource_props_map.get(resource.identifier, {})
                resource.properties.update(props)
                
                if not resource.version:
                    resource.version = (
                        props.get("summary|version", "") or
                        props.get("config|product|version", "") or
                        props.get("System|product_version", "")
                    )
                
                if not resource.build:
                    resource.build = (
                        props.get("summary|build", "") or
                        props.get("config|product|build", "") or
                        props.get("System|product_build", "")
                    )
            
            return resources
            
        except httpx.TimeoutException:
            log.warning("Timeout fetching properties, returning resources without properties")
            return resources
        except httpx.RequestError as e:
            log.warning(f"Failed to fetch properties: {e}")
            return resources
    
    def ping(self) -> bool:
        """Test API connectivity."""
        try:
            url = f"{self.server}{self.API_BASE}/api/versions/current"
            response = self._client.get(url, headers=self._get_headers())
            return response.status_code == 200
        except Exception:
            return False
    
    @property
    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self._authenticated
