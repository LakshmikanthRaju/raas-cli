# RaaS Compatibility

RaaS deployments differ by product release, enabled services, reverse-proxy layout, authentication mode, and role permissions.

## RPC paths

The client tries:

1. `/rpc`
2. `/raas/rpc`

A path fallback occurs only for endpoint compatibility errors such as HTTP 404 or 405. Authentication and server errors are not silently treated as path mismatch.

## Authentication

Supported flows:

- username/password login returning a JWT/session
- cached JWT/session reuse
- CSP API token flow where configured

The exact identity provider and role permissions remain deployment-specific.

## Common resources used

- `cmd`: submit and inspect Salt commands
- `ret`: retrieve command returns
- `job`: saved jobs
- `fs`: file-server operations
- `tgt`: target groups
- `pillar`: pillar definitions
- `minion`: minion inventory
- `master`: Salt master inventory
- `api`: API version/discovery
- `license`: license details

## Known payload variation

Some releases return lists directly; others return objects such as `{"results": [...]}`. The client and command helpers normalize both forms where known.

The state execution payload follows the nested structure used by RaaS:

```yaml
cmd: local
fun: state.apply
tgt:
  '*':
    tgt: '*'
    tgt_type: glob
arg:
  arg:
    - fleet_settings.states.fleet
  kwarg:
    saltenv: fleet_mgmt
    test: true
```

## Validation before production

Run these against a non-production endpoint using the same RaaS release and role:

```bash
scc status
scc doctor
scc system-info
scc list
scc fs-list --env base
scc exec test.ping --target '*'
scc run /path/to/read-only-test.sls --target '*' --test
```

Confirm the service account can perform only the required operations.
