# Git-to-RaaS workflow

## Objective

Give users one understandable path from Git-managed configuration to safe Salt execution:

1. reusable Salt states come from a shared source;
2. instance/environment/version values come from a customer-controlled source;
3. the customer repository handles review, approval, branch protection, and merge;
4. SCC pulls the requested refs, validates the selected content, and displays exact commits;
5. the state tree is published to the RaaS file server;
6. SCC submits `state.apply` directly to an existing target group and tracks the returned JID;
7. `test=True` is reviewed before `test=False`.

SCC does not create or require a separate approval manifest. Git remains the approval system.

## Ownership model

### Shared state source

Typical contents:

- `.sls` state files;
- `defaults.yaml`;
- `map.jinja`;
- Jinja templates and scripts;
- supporting files used by `salt://` references.

The CLI copies and validates the complete resource directory recursively. It does not assume a fixed three-file shape.

### Customer-values source

Typical contents:

- environment or instance settings;
- release-specific values;
- customer configuration templates;
- site-specific parameters.

This source can be private and follows the customer's existing pull-request and change-approval process. The configured ref may be a branch, protected tag, or immutable commit.

## Source configuration

Repository metadata is separate from the RaaS connection profile:

```yaml
version: 1
default_states_source: vcf-salt
default_data_source: customer-values
sources:
  vcf-salt:
    kind: states
    url: https://git.example.com/shared/vcf-salt.git
    ref: v9.1.1
    root: vcf-infra
    layout: "{resource}"
    auth: credential-helper
  customer-values:
    kind: data
    url: ssh://git@git.example.com/customer/config-values.git
    ref: main
    root: .
    layout: "{environment}/{version}/{resource}/values.yaml"
    auth: ssh
```

This file never contains a password, token, SSH private key, or RaaS credential.

## Authentication

Recommended order:

1. SSH agent and managed `known_hosts` for SSH sources;
2. enterprise Git credential helper for HTTPS sources;
3. OS keychain token through `scc repo login <source>`;
4. source-specific CI secret through `SCC_GIT_TOKEN_<SOURCE_NAME>`.

SCC sets `GIT_TERMINAL_PROMPT=0` so unattended operations fail instead of waiting forever. SSH mode uses batch authentication. Git operations have a bounded timeout, configurable with `SCC_GIT_TIMEOUT`.

## Plan output

`scc deploy <resource>` contacts Git but does not contact RaaS. It displays:

- resource and selected state entrypoint;
- environment, version, and values selectors;
- state source name, URL, configured ref, exact commit, and commit timestamp;
- values source name, URL, configured ref, exact commit, and selected `values.yaml` path;
- every packaged file path, type, size, and SHA-256;
- validation warnings.

The validated content is staged under `.scc/work/<resource>/` for the next operation. No separate approval artifact is generated.

## Publication and values modes

### Runtime values mode (default)

`--values-mode runtime` passes `values.yaml` as execution-scoped pillar data in the direct `state.apply` request. It is not uploaded to the Salt file server and is not persisted as a RaaS pillar association.

### Pillar data mode

`--values-mode pillar` creates or updates managed pillar data and associates it with the selected target group. Use it only when the operating model requires persistent RaaS pillar data. This is an explicit advanced mode, not the normal customer path.

### No data

`--without-data` or `--values-mode none` uses only state defaults.

## RaaS publication and direct execution

The reusable state directory keeps its repository-relative path in the selected RaaS file-server environment. For example, `vcf-infra/cluster-drs` is published as `/vcf-infra/cluster-drs`. Customer `values.yaml` is never uploaded to the file server.

Dry-run and apply submit `state.apply` directly with the target-group scope, selected Salt environment, `test=True` or `test=False`, and execution-scoped pillar values. RaaS returns a JID, which SCC monitors. No persistent saved job is created unless `--save-job` is explicitly supplied. The optional saved job contains no customer values and is pinned to `test=False` - it applies for real on every `scc job-run`.

## Approval boundary

The customer repository is the approval boundary:

```text
configuration change
    -> pull request
    -> review / policy checks
    -> merge to protected branch or tag
    -> SCC pull, validate, publish, and execute
```

A normal SCC sequence is:

```bash
scc deploy dns --environment prod --version 9.1.1
scc deploy dns --environment prod --version 9.1.1 --mode dry-run --target-group vcf-prod
# review test=True results and complete the customer's approval process
scc deploy dns --environment prod --version 9.1.1 --mode apply --target-group vcf-prod
```

By default, each command refreshes the configured Git refs and displays the exact commits it resolved. Apply then shows the target group, state commit, values commit, and `test=False`, and requires explicit confirmation before any RaaS mutation.

## Production recommendations

- Use protected branches and pull-request approval in the customer-values repository.
- Prefer protected tags or commit SHAs for reproducible production runs.
- Store the displayed commit IDs, dry-run result, RaaS JID with the change ticket.
- Use separate RaaS profiles and Git sources for lab and production.
- Start with one target group in a non-production environment.
- Keep runtime data as the default unless persistence is explicitly required.
- Treat `--no-verify-tls`, broad targets, `--force`, and `--yes` as exceptional controls.

## Apply safety boundary

`--mode apply` does not require another approval file. It:

1. refreshes and validates the configured Git refs unless `--no-refresh` is explicitly used;
2. displays exact state and values commits and the selected `values.yaml` path;
3. displays the target group and `test=False` intent;
4. requires typed confirmation before RaaS files are published or direct execution is submitted.
