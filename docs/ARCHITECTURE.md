# Architecture

## Design goals

- Keep the common customer journey simple: configure sources once, preview, dry-run, approve in Git, apply.
- Keep reusable Salt states and customer-specific values under independent Git ownership and release lifecycles.
- Keep RaaS profiles, Git source metadata, and credentials separated.
- Preserve low-level RaaS operations for expert users without requiring them for normal onboarding.
- Make deployments traceable to exact Git commits, target groups, and RaaS JIDs.

## Layers

### CLI and interactive UX

- `salt_config_cli/cli/main.py` — RaaS, Salt, file-server, saved-job, desired-state commands, and launch dashboard.
- `salt_config_cli/cli/repo_cmds.py` — named Git source setup, testing, secure credential onboarding, import/export, and cache refresh.
- `salt_config_cli/cli/workflow_cmds.py` — high-level plan/publish/dry-run/apply orchestration.
- `salt_config_cli/cli/discovery.py` — command search, examples, and network-free tutorials.
- `salt_config_cli/cli/profile_cmds.py` — named RaaS profiles and backward-compatible Git setting migration.
- `salt_config_cli/cli/theme_cmds.py` and `salt_config_cli/ui/` — themes, plain mode, responsive tables, prompts, errors, progress, and summaries.

### Git source and workspace layer

- `salt_config_cli/core/repositories.py` — strict non-secret repository schema, source defaults, path discovery, legacy migration, atomic persistence, and keychain token resolution.
- `salt_config_cli/services/git_repository.py` — system-Git synchronization, shallow cache, locking, authentication environment, content validation, data layout resolution, and local deployment workspace assembly.

### RaaS clients

- `salt_config_cli/api/client.py` — authentication, token cache, RPC path fallback, and RaaS convenience operations.
- `salt_config_cli/api/ops_client.py` — optional VCF Operations integration.
- `salt_config_cli/api/token_cache.py` — per-server/user session cache.

### Desired-state core

- `core/models.py`, `core/state.py`, `core/plan.py`, and `core/drift.py` — local declarative resource planning, persistence, drift detection, and remediation.
- `handlers/` — resource-specific operations for jobs, pillars, state files, and target groups.

## Configuration separation

```text
~/.scc/config.yaml
    named RaaS profiles, non-secret connection fields, global theme

~/.scc/repositories.yaml
    named Git URLs, refs, roots, layouts, and authentication mode

OS keychain / SSH agent / Git credential helper / CI environment
    passwords, CSP tokens, Git tokens, SSH keys

.scc/work/<resource>/
    validated local states and selected customer values used only for runtime execution
```

Older root-level `git_*` settings are read only to migrate them into `repositories.yaml`. New repository commands never write Git metadata into the RaaS profile document.

## Git-to-RaaS execution path

```text
User / CI
  |
  +--> RaaS profile selection (--profile / SCC_PROFILE)
  |
  +--> Git source selection (named default or --states-source/--values-source)
  |
  v
GitRepositoryService
  +--> bounded system-git fetch
  +--> SSH agent / credential helper / keychain token
  +--> private shallow cache + stale-lock recovery
  +--> exact commit resolution
  |
  v
ContentWorkspaceService
  +--> resolve complete state resource tree
  +--> resolve environment/version customer `values.yaml`
  +--> reject traversal, symlinks, oversized/binary/invalid YAML content
  +--> copy a clean local workspace atomically
  +--> compute file hashes for display and diagnostics
  |
  +--> mode=plan: display commits/files and stop; no RaaS calls
  |
  +--> mode=publish/dry-run/apply
          +--> upload complete state tree to its repository-relative RaaS path
          +--> never upload customer values to the file server
          +--> optionally persist values as RaaS pillar only when explicitly requested
          +--> dry-run: direct state.apply with test=True + runtime pillar
          +--> apply: display commits + target, confirm, direct state.apply test=False
          +--> receive JID, poll, and render per-minion results
          +--> create a safe saved job only when --save-job is explicit
```

## Approval responsibility

The customer's Git platform owns content approval through pull requests, reviewers, status checks, protected branches, and protected tags. SCC does not duplicate this process.

SCC is responsible for:

- pulling the requested refs;
- resolving and displaying exact commits;
- validating the selected state tree and customer data;
- making `plan` a no-RaaS operation;
- defaulting the first execution to `test=True`;
- confirming target and commits before `test=False`;
- including commit IDs in command output and optional saved-job descriptions.

## Extension points

- Add another `RepositorySource.kind` only with a schema migration and tests.
- Add content validators inside `ContentWorkspaceService` without coupling them to Click.
- Add deployment stages in `workflow_cmds.py` by invoking stable low-level commands or moving reusable behavior into services.
- Add typed RaaS convenience methods to `AriaConfigClient` instead of constructing ad-hoc RPC payloads in new commands.
- Add sanitized tutorials/examples without network calls.

## Static KB solution catalog

KB discovery is a read-only layer above the existing Git-to-RaaS workflow. `KBCatalogService` loads reviewed solution definitions from the reusable-state repository, validates the single mapped state, and provides lexical search and applicability checks. `scc kb plan/execute` resolves that resource state and invokes the same `scc deploy` implementation with its derived resource and `.sls` entrypoint. This avoids a second execution engine and preserves direct RaaS JID tracking, runtime values, profiles, themes, and safety controls.
