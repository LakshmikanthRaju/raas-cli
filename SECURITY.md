# Security policy

## Reporting

Report suspected vulnerabilities privately to the project maintainers. Do not include real RaaS credentials, customer values, private repository tokens, or production logs in a public issue.

## Credential handling

SCC does not intentionally persist passwords, CSP tokens, Git tokens, or SSH private keys in YAML.

- RaaS credentials use the OS keychain, environment, stdin, protected file, or masked prompt.
- Git HTTPS tokens use the OS keychain or a source-specific environment variable.
- SSH repositories use the system SSH agent and `known_hosts`.
- Git credential-helper mode delegates to the user's configured Git helper.
- Tokens are passed to Git through a temporary askpass process, not embedded in URLs or command arguments.

Never place secrets in:

- `~/.scc/config.yaml`;
- `~/.scc/repositories.yaml`;
- command-line URLs;
- customer values committed without the customer's approved secret-management policy;
- examples, tests, screenshots, or bug reports.

## Git and content safety

- Repository URLs with embedded HTTP credentials and values beginning with `-` are rejected.
- Refs reject whitespace, option-like values, traversal sequences, and reflog expressions.
- Repository roots/layouts reject absolute paths and `..` traversal.
- Git operations are bounded by `SCC_GIT_TIMEOUT` and use non-interactive authentication.
- Cache locks recover from killed processes.
- Deployable content rejects symlinks, non-UTF-8 files, invalid YAML, files over 10 MiB, and packages over 100 MiB.
- Production refs should use protected tags or commit SHAs where possible.

## Deployment safety

- `scc deploy` defaults to `plan` and makes no RaaS changes.
- `dry-run` submits `state.apply` directly with `test=True` and execution-scoped pillar values.
- Git pull-request review and branch/tag policy are the approval mechanism; SCC does not create a separate approval artifact.
- `apply` refreshes and validates the configured refs by default, displays exact commits and target group, and requires explicit confirmation before RaaS mutation.
- Runtime-only private values injection is the default; persistent pillar publication is opt-in.
- Persistent saved-job creation is opt-in through `--save-job`; the saved job is fixed to `test=True` and contains no customer values. Existing state/job mutation confirmations remain in effect.

Store the displayed commit IDs, dry-run output, RaaS JID with the change record when operational traceability is required.

## TLS

Use trusted CA certificates in production. `--no-verify-tls` and profile-level TLS disablement are intended only for controlled testing and should not be used as a long-term workaround.

## Supported versions

Security fixes are applied to the latest release line. Users should upgrade before reporting behavior from older generated packages.

## KB solution catalog safety

Treat the catalog as executable supply-chain metadata. Production mappings must be reviewed and versioned with the referenced states. SCC validates file existence and mapping consistency but cannot establish that a KB resolution is operationally correct; maintainers must test supported product versions and assign `validated`/`verified` status deliberately. The AI agent must not generate mappings or execute an uncataloged state. Fictional examples use `DEMO-*` IDs and `example.invalid` URLs.
