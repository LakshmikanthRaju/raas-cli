# Restored Demo Capabilities

The 0.6.0 implementation retains the capabilities visible in the earlier Salt Config CLI demo:

## Launch and discovery

- large SCC ASCII launch screen
- active server, user, and workspace context
- quick-start and command-discovery panels
- fully themed group and command help, command search, examples, tutorial, and tab completion
- command response cards, contextual metadata, Rich result tables, progress, empty states, summaries, and next steps
- history-aware interactive shell with numbered shortcuts and command completion

## File-server operations

- environment-specific tree view
- recursive folder download with preview and overwrite handling
- recursive upload with include/exclude filters, dry-run, confirmation, and force mode
- remote file edit with local editor and diff

## Fleet settings workflow

- DNS and NTP content under one fleet-settings tree
- creation and execution of reusable `state.apply` jobs
- dry-run compliance result showing compliant and non-compliant controls
- current-versus-desired values for detected differences
- apply run with live per-minion progress
- final compliance rendering after remediation

## Additional production improvements

- missing UI and discovery packages rebuilt
- state run changed to dry-run by default
- guarded mutating saved jobs and raw RPC operations
- embedded environment configuration removed
- bundled secrets and internal values sanitized
- packaging, CI, release checks, security guidance, and compatibility docs added

## UX consistency added in 0.4.0

- `scc help`, `scc --help`, `scc help <command>`, and `<command> --help` share the SCC theme.
- Interactive command output starts with the operation, target, server, environment, and safety mode where relevant.
- Long-running operations use spinners, elapsed time, or per-minion live progress.
- Completed operations end with an outcome summary and useful follow-up commands.
- Empty results explain what happened and suggest a safe next action.
- Machine-readable JSON/YAML paths remain undecorated for scripts.


## Connection profiles restored in 0.5.0

- named lab, staging, production, or tenant profiles
- active profile shown on the launch screen and command headers
- interactive create, edit, switch, clone, test, login/logout, and delete flows
- non-secret YAML import/export and effective-configuration inspection
- environment overrides for CI/CD and one-command profile selection
- legacy flat configuration migration without persisting credentials

## Professional themes added in 0.6.0

- Ocean, Enterprise, Graphite, Forest, Amber, and High Contrast palettes
- global and per-profile theme persistence
- live preview and interactive selection
- one-command `--theme` and `SCC_THEME` overrides
- `scc theme disable` / `plain` mode for conventional terminal output without panels, colour, decorative icons, or animation
