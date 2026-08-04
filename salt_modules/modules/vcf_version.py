"""
Salt execution module to get VCF component versions.

This module auto-detects the component type from the vcfops_resource_kind grain
and fetches version information using the appropriate API.

Credentials are read from pillar data under 'vcf_credentials'.

Pillar structure:
    vcf_credentials:
      nsx:
        username: admin
        password: secret
      vcenter:
        username: administrator@vsphere.local
        password: secret
      sddc_manager:
        username: admin@local
        password: secret

Usage:
    salt '*' vcf_version.get_version
    salt 'nsx-*' vcf_version.get_nsx_version
    salt 'vcenter-*' vcf_version.get_vcenter_version
    salt 'sddc-*' vcf_version.get_sddc_manager_version
    salt 'esxi-*' vcf_version.get_esxi_version

Deployment:
    1. Copy this file to /srv/salt/_modules/vcf_version.py on the Salt Master
       OR upload via: scc upload vcf_version.py --path /_modules/vcf_version.py
    2. Sync modules: salt '*' saltutil.sync_modules
       OR via CLI: scc exec saltutil.sync_modules --target "*"
"""

import logging

log = logging.getLogger(__name__)

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


def __virtual__():
    """Only load if requests is available."""
    if not HAS_REQUESTS:
        return False, "The requests library is required for vcf_version module"
    return True


def _get_credentials(component, pillar_override=None):
    """
    Get credentials from pillar for a component.
    
    Args:
        component: The component name (nsxm, vcenter, sddcm)
        pillar_override: Optional dict to use instead of __pillar__ (for inline pillar)
    
    Returns:
        Tuple of (username, password, host) or (None, None, None) if not found
    """
    pillar_source = pillar_override if pillar_override is not None else __pillar__
    creds = pillar_source.get('vcf_credentials', {}).get(component, {})
    return creds.get('username'), creds.get('password'), creds.get('host')


def _create_session(verify_ssl=False, timeout=30):
    """Create a requests session with common settings."""
    session = requests.Session()
    session.verify = verify_ssl
    session.timeout = timeout
    return session


def get_nsx_version(host=None, username=None, password=None, verify_ssl=False, pillar=None):
    """
    Get NSX Manager version.
    
    Uses Basic Auth. Credentials can be passed directly or read from pillar.
    
    Args:
        host: NSX Manager hostname/IP (default: from pillar, then grains, then localhost)
        username: Admin username (default: from pillar)
        password: Admin password (default: from pillar)
        verify_ssl: Verify SSL certificates (default: False)
        pillar: Optional dict of pillar data (for inline pillar via scc exec --pillar-file)
    
    Returns:
        dict: Version info with 'version', 'build', or 'error'
    
    CLI Example:
        salt 'nsx-*' vcf_version.get_nsx_version
        salt 'nsx-*' vcf_version.get_nsx_version username=admin password=secret
        salt 'nsx-*' vcf_version.get_nsx_version host=nsx-1.example.com
    """
    pillar_user, pillar_pass, pillar_host = _get_credentials('nsxm', pillar)
    
    if host is None:
        host = pillar_host or __grains__.get('fqdn') or __grains__.get('host') or __grains__.get('vcfops_resource_name') or 'localhost'
    
    if username is None or password is None:
        username = username or pillar_user
        password = password or pillar_pass
    
    if not username or not password:
        return {
            "error": "No NSX credentials provided. Set vcf_credentials:nsx in pillar or pass username/password",
            "version": None,
            "build": None,
        }
    
    try:
        session = _create_session(verify_ssl=verify_ssl)
        session.auth = (username, password)
        
        resp = session.get(f"https://{host}/api/v1/node")
        
        if resp.ok:
            data = resp.json()
            return {
                "version": data.get('product_version', 'Unknown'),
                "build": data.get('product_build_number', ''),
                "node_id": data.get('node_id', ''),
                "error": None,
            }
        return {
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            "version": None,
            "build": None,
        }
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {e}", "version": None, "build": None}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out", "version": None, "build": None}
    except Exception as e:
        return {"error": str(e), "version": None, "build": None}


def get_vcenter_version(host=None, username=None, password=None, verify_ssl=False, pillar=None):
    """
    Get vCenter version.
    
    Uses session-based auth via /api/session endpoint.
    
    Args:
        host: vCenter hostname/IP (default: from pillar, then grains, then localhost)
        username: Admin username (default: from pillar)
        password: Admin password (default: from pillar)
        verify_ssl: Verify SSL certificates (default: False)
        pillar: Optional dict of pillar data (for inline pillar via scc exec --pillar-file)
    
    Returns:
        dict: Version info with 'version', 'build', or 'error'
    
    CLI Example:
        salt 'vcenter-*' vcf_version.get_vcenter_version
        salt 'vcenter-*' vcf_version.get_vcenter_version host=vcenter-1.example.com
        salt 'vcenter-*' vcf_version.get_vcenter_version username=admin@vsphere.local password=secret
    """
    pillar_user, pillar_pass, pillar_host = _get_credentials('vcenter', pillar)
    
    if host is None:
        host = pillar_host or __grains__.get('fqdn') or __grains__.get('host') or __grains__.get('vcfops_resource_name') or 'localhost'
    
    if username is None or password is None:
        username = username or pillar_user
        password = password or pillar_pass
    
    if not username or not password:
        return {
            "error": "No vCenter credentials provided. Set vcf_credentials:vcenter in pillar or pass username/password",
            "version": None,
            "build": None,
        }
    
    try:
        session = _create_session(verify_ssl=verify_ssl)
        
        # Authenticate and get session token
        auth_resp = session.post(
            f"http://{host}/api/session",
            auth=(username, password),
        )
        
        if not auth_resp.ok:
            return {
                "error": f"Authentication failed: HTTP {auth_resp.status_code}",
                "version": None,
                "build": None,
            }
        
        # vCenter 7.x returns the token directly as a string
        token = auth_resp.json() if auth_resp.headers.get('content-type', '').startswith('application/json') else auth_resp.text.strip('"')
        session.headers['vmware-api-session-id'] = token
        
        # Get version info
        resp = session.get(f"http://{host}/api/appliance/system/version")
        
        if resp.ok:
            data = resp.json()
            return {
                "version": data.get('version', 'Unknown'),
                "build": data.get('build', ''),
                "type": data.get('type', ''),
                "error": None,
            }
        return {
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            "version": None,
            "build": None,
        }
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {e}", "version": None, "build": None}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out", "version": None, "build": None}
    except Exception as e:
        return {"error": str(e), "version": None, "build": None}


def get_sddc_manager_version(host=None, username=None, password=None, verify_ssl=False, pillar=None):
    """
    Get SDDC Manager version.
    
    Uses bearer token auth via /v1/tokens endpoint.
    
    Args:
        host: SDDC Manager hostname/IP (default: from pillar, then grains, then localhost)
        username: Admin username (default: from pillar)
        password: Admin password (default: from pillar)
        verify_ssl: Verify SSL certificates (default: False)
        pillar: Optional dict of pillar data (for inline pillar via scc exec --pillar-file)
    
    Returns:
        dict: Version info with 'version', 'build', or 'error'
    
    CLI Example:
        salt 'sddc-*' vcf_version.get_sddc_manager_version
        salt 'sddc-*' vcf_version.get_sddc_manager_version username=admin@local password=secret
        salt 'sddc-*' vcf_version.get_sddc_manager_version host=sddc-1.example.com
    """
    pillar_user, pillar_pass, pillar_host = _get_credentials('sddc_manager', pillar)
    
    if host is None:
        host = pillar_host or __grains__.get('fqdn') or __grains__.get('host') or __grains__.get('vcfops_resource_name') or 'localhost'
    
    if username is None or password is None:
        username = username or pillar_user
        password = password or pillar_pass
    
    if not username or not password:
        return {
            "error": "No SDDC Manager credentials provided. Set vcf_credentials:sddc_manager in pillar or pass username/password",
            "version": None,
            "build": None,
        }
    
    try:
        session = _create_session(verify_ssl=verify_ssl)
        
        # Get bearer token
        auth_resp = session.post(
            f"https://{host}/v1/tokens",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"},
        )
        
        if not auth_resp.ok:
            return {
                "error": f"Authentication failed: HTTP {auth_resp.status_code}",
                "version": None,
                "build": None,
            }
        
        token = auth_resp.json().get('accessToken')
        if not token:
            return {
                "error": "No access token in authentication response",
                "version": None,
                "build": None,
            }
        
        session.headers['Authorization'] = f'Bearer {token}'
        
        # Get SDDC Manager info from /v1/sddc-managers
        resp = session.get(f"https://{host}/v1/sddc-managers")
        
        if resp.ok:
            data = resp.json()
            elements = data.get('elements', [])
            
            if not elements:
                return {
                    "error": "No SDDC Manager found in response",
                    "version": None,
                    "build": None,
                }
            
            sddc_mgr = elements[0]
            version_str = sddc_mgr.get('version', 'Unknown')
            
            version_parts = version_str.split('.') if version_str else []
            version = '.'.join(version_parts[:3]) if len(version_parts) >= 3 else version_str
            build = version_parts[-1] if len(version_parts) > 3 else ''
            
            return {
                "version": version,
                "build": build,
                "full_version": version_str,
                "fqdn": sddc_mgr.get('fqdn', ''),
                "ip_address": sddc_mgr.get('ipAddress', ''),
                "domain_id": sddc_mgr.get('domain', {}).get('id', ''),
                "sddc_manager_id": sddc_mgr.get('id', ''),
                "error": None,
            }
        return {
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            "version": None,
            "build": None,
        }
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {e}", "version": None, "build": None}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out", "version": None, "build": None}
    except Exception as e:
        return {"error": str(e), "version": None, "build": None}


def get_esxi_version():
    """
    Get ESXi version from grains.
    
    No API call needed - ESXi version info is available in Salt grains.
    
    Returns:
        dict: Version info with 'version', 'build'
    
    CLI Example:
        salt 'esxi-*' vcf_version.get_esxi_version
    """
    return {
        "version": __grains__.get('osrelease', __grains__.get('kernelrelease', 'Unknown')),
        "build": __grains__.get('osbuild', __grains__.get('build', '')),
        "os": __grains__.get('os', ''),
        "error": None,
    }


def get_aria_operations_version(host=None, username=None, password=None, verify_ssl=False, pillar=None):
    """
    Get Aria Operations (vROps) version.
    
    Uses token auth via /suite-api/api/auth/token/acquire endpoint.
    
    Args:
        host: Aria Operations hostname/IP (default: from pillar, then grains, then localhost)
        username: Admin username (default: from pillar)
        password: Admin password (default: from pillar)
        verify_ssl: Verify SSL certificates (default: False)
        pillar: Optional dict of pillar data (for inline pillar via scc exec --pillar-file)
    
    Returns:
        dict: Version info with 'version', 'build', or 'error'
    
    CLI Example:
        salt 'vrops-*' vcf_version.get_aria_operations_version
        salt 'vrops-*' vcf_version.get_aria_operations_version host=vrops-1.example.com
    """
    pillar_user, pillar_pass, pillar_host = _get_credentials('aria_operations', pillar)
    
    if host is None:
        host = pillar_host or __grains__.get('fqdn') or __grains__.get('host') or __grains__.get('vcfops_resource_name') or 'localhost'
    
    if username is None or password is None:
        username = username or pillar_user
        password = password or pillar_pass
    
    if not username or not password:
        return {
            "error": "No Aria Operations credentials provided. Set vcf_credentials:aria_operations in pillar",
            "version": None,
            "build": None,
        }
    
    try:
        session = _create_session(verify_ssl=verify_ssl)
        
        # Get auth token
        auth_resp = session.post(
            f"https://{host}/suite-api/api/auth/token/acquire",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        
        if not auth_resp.ok:
            return {
                "error": f"Authentication failed: HTTP {auth_resp.status_code}",
                "version": None,
                "build": None,
            }
        
        token = auth_resp.json().get('token')
        session.headers['Authorization'] = f'OpsToken {token}'
        
        # Get version info
        resp = session.get(
            f"https://{host}/suite-api/api/versions/current",
            headers={"Accept": "application/json"},
        )
        
        if resp.ok:
            data = resp.json()
            # Handle different response formats
            if isinstance(data, dict):
                version = data.get('releaseName', data.get('version', 'Unknown'))
                build = data.get('buildNumber', data.get('build', ''))
            else:
                version = str(data)
                build = ''
            
            return {
                "version": version,
                "build": build,
                "error": None,
            }
        return {
            "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
            "version": None,
            "build": None,
        }
    except requests.exceptions.ConnectionError as e:
        return {"error": f"Connection failed: {e}", "version": None, "build": None}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out", "version": None, "build": None}
    except Exception as e:
        return {"error": str(e), "version": None, "build": None}


def get_version(host=None, username=None, password=None, verify_ssl=False, pillar=None):
    """
    Auto-detect component type from grain and get version.
    
    Reads the vcfops_resource_kind grain to determine which API to call.
    Falls back to checking os grain for ESXi hosts.
    
    Args:
        host: Optional host override (defaults to pillar, then grains)
        username: Optional username (overrides pillar)
        password: Optional password (overrides pillar)
        verify_ssl: Verify SSL certificates (default: False)
        pillar: Optional dict of pillar data (for inline pillar via scc exec --pillar-file)
    
    Returns:
        dict: Version info with 'version', 'build', 'resource_kind', or 'error'
    
    CLI Example:
        salt '*' vcf_version.get_version
        salt '*' vcf_version.get_version username=admin password=secret
        scc exec vcf_version.get_version --pillar-file vcf_credentials.yaml
    """
    resource_kind = __grains__.get('vcfops_resource_kind', '').lower()
    os_grain = __grains__.get('os', '').lower()
    
    # Dispatch table mapping resource kinds to version functions
    dispatch = {
        'nsxm': get_nsx_version,
        'nsx_manager': get_nsx_version,
        'nsx-manager': get_nsx_version,
        'vcenter': get_vcenter_version,
        'vc': get_vcenter_version,
        'vcsa': get_vcenter_version,
        'sddc_manager': get_sddc_manager_version,
        'sddc-manager': get_sddc_manager_version,
        'sddcm': get_sddc_manager_version,
        'sddc': get_sddc_manager_version,
        'cloudbuilder': get_sddc_manager_version,
        'esxi': get_esxi_version,
        'host': get_esxi_version,
        'vmkernel': get_esxi_version,
        'aria_operations': get_aria_operations_version,
        'ops': get_aria_operations_version,
        'vrops': get_aria_operations_version,
        'vrealize_operations': get_aria_operations_version,
    }
    
    # Try to match resource_kind first
    func = dispatch.get(resource_kind)
    
    # Fall back to OS detection for ESXi
    if func is None and os_grain in ('vmkernel', 'esxi'):
        func = get_esxi_version
        resource_kind = 'esxi'
    
    if func:
        # ESXi doesn't need credentials or host
        if func == get_esxi_version:
            result = func()
        else:
            kwargs = {'verify_ssl': verify_ssl, 'pillar': pillar}
            if host is not None:
                kwargs['host'] = host
            if username is not None:
                kwargs['username'] = username
            if password is not None:
                kwargs['password'] = password
            result = func(**kwargs)
        
        result['resource_kind'] = resource_kind
        result['minion_id'] = __grains__.get('id', '')
        return result
    
    return {
        "error": f"Unknown resource kind: '{resource_kind}'. Set vcfops_resource_kind grain or use specific function.",
        "resource_kind": resource_kind,
        "minion_id": __grains__.get('id', ''),
        "known_kinds": list(dispatch.keys()),
        "version": None,
        "build": None,
    }


def get_all_versions(target_components=None, pillar=None):
    """
    Get versions for all VCF components this minion can reach.
    
    Useful for minions that can access multiple components (e.g., jump hosts).
    
    Args:
        target_components: List of components to query (default: all configured in pillar)
        pillar: Optional dict of pillar data (for inline pillar via scc exec --pillar-file)
    
    Returns:
        dict: Component name -> version info
    
    CLI Example:
        salt 'jumphost' vcf_version.get_all_versions
        salt 'jumphost' vcf_version.get_all_versions target_components='["nsx", "vcenter"]'
        scc exec vcf_version.get_all_versions --pillar-file vcf_credentials.yaml
    """
    pillar_source = pillar if pillar is not None else __pillar__
    creds = pillar_source.get('vcf_credentials', {})
    
    if target_components is None:
        target_components = list(creds.keys())
    
    component_funcs = {
        'nsx': get_nsx_version,
        'vcenter': get_vcenter_version,
        'sddc_manager': get_sddc_manager_version,
        'aria_operations': get_aria_operations_version,
    }
    
    results = {}
    for component in target_components:
        func = component_funcs.get(component)
        if func:
            comp_config = creds.get(component, {})
            host = comp_config.get('host')
            results[component] = func(host=host, pillar=pillar)
        else:
            results[component] = {"error": f"Unknown component: {component}"}
    
    return results
