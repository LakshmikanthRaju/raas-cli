# Safety Model

## Defaults

- `scc run` uses `test=True` by default.
- Applying a state requires `--no-test` and confirmation.
- Potentially mutating saved jobs require confirmation.
- Deletion and destructive desired-state actions require confirmation.
- Recursive uploads support `--dry-run` and do not overwrite without `--force`.
- Raw RPC calls require typed confirmation unless explicitly declared read-only.

## Automation

Non-interactive approval flags exist for reviewed automation, but they are not a substitute for authorization, change-management, maintenance-window, or rollback controls.

## Read-only classification

The saved-job fast path intentionally uses a narrow allowlist. Unknown functions are treated as potentially mutating. Broad namespaces are not assumed safe because a namespace may contain both read and write functions.

## Secrets

The CLI masks URLs containing user information, supports OS keyring storage, warns about command-line passwords, and excludes secrets from settings display. Operators remain responsible for terminal capture, logs, shell history, and exported result files.
