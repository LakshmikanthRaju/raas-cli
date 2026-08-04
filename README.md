# Salt Config CLI (`scc`)

Salt Config CLI is an interactive and scriptable command-line interface for Salt/RaaS operations. It is designed to make a Git-to-RaaS configuration workflow feel simple without hiding safety, provenance, or advanced controls.

The normal customer journey is:

```text
shared saltext-vcf states repo ──> SCC validate/publish ──> RaaS file server
private customer values repo ──> SCC runtime values ───────> direct state.apply ──> target group
                                             │
                                             └─ RaaS JID and per-target results
```

SCC also provides a static KB-to-Salt solution catalog, file-server browsing, minion execution, target groups, pillars, saved jobs, live job results, desired-state drift workflows, named RaaS profiles, professional themes, plain terminal output, and a guarded raw RPC escape hatch.

> Start against a non-production RaaS environment and validate the RPC methods and permissions used by your RaaS version before operational rollout.

## Why the Git workflow is split into two sources

A production configuration usually has two different lifecycles:

1. **Reusable Salt content** — open/shared states, defaults, mapping Jinja, templates, and supporting files. For example, a `vcf-salt` repository maintained by the product or community.
2. **Customer-specific values** — instance, environment, site, and release-specific values. This commonly lives in a private repository where normal pull-request review and approval occur before merge.

SCC keeps these sources independent. It does not write repository credentials into the RaaS profile file or `repositories.yaml`.

The customer-values repository remains the single approval system. Customers use their normal pull-request review, branch protection, and merge process. SCC pulls the requested content, validates it, displays the resolved commits and files, and records commit IDs in the RaaS job description and execution output. It does not create or require a separate approval manifest.

## Installation

Python 3.10 or later and the system `git` executable are required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install .

scc --version
```

The package installs equivalent `scc`, `salt-config`, and `raas` entry points.

## Five-minute onboarding

### 1. Create a RaaS connection profile

```bash
scc connect --name lab
scc profile use lab
scc profile test lab
```

The password or CSP token is stored separately in the OS keychain. Profile YAML contains only non-secret connection settings.

### 2. Configure the Git sources

The guided setup is the easiest path:

```bash
scc repo setup
scc repo test --all
```

A non-interactive equivalent is:

```bash
scc repo add vcf-salt \
  --kind states \
  --url https://git.example.com/shared/vcf-salt.git \
  --ref main \
  --root vcf-infra \
  --layout '{resource}' \
  --default

scc repo add customer-values \
  --kind data \
  --url ssh://git@git.example.com/customer/config-values.git \
  --ref main \
  --layout '{environment}/{version}/{resource}/values.yaml' \
  --auth ssh \
  --default
```

Repository metadata is stored in a separate file, normally `~/.scc/repositories.yaml` next to the RaaS profile configuration. It can also be workspace-specific at `./.scc/repositories.yaml`.

For private repositories, SCC reuses normal Git mechanisms:

- SSH agent and `known_hosts` with `--auth ssh`
- Git credential helper with `--auth credential-helper`
- OS keychain token with `--auth token` and `scc repo login <source>`
- source-specific environment variable such as `SCC_GIT_TOKEN_CUSTOMER_VALUES`

Tokens are never stored in YAML or embedded into the repository URL.

### 3. Ask SCC for a plan

```bash
scc deploy dns \
  --environment prod \
  --version 9.1.1
```

The default mode is `plan`. SCC:

- fetches the configured refs using the system Git client;
- resolves the complete state resource tree recursively;
- resolves the private environment/version `values.yaml` file;
- validates path safety, UTF-8 content, YAML, symlinks, and package limits;
- creates a local review workspace;
- displays source URLs, refs, exact commits, selected values path, entrypoint, file sizes, and SHA-256 hashes;
- makes **no RaaS changes**.

No approval artifact is created. The customer repository's pull-request and protected-branch workflow remains the approval mechanism.

### 4. Publish and run safely

```bash
scc deploy dns \
  --environment prod \
  --version 9.1.1 \
  --mode dry-run \
  --target-group vcf-prod
```

This single command uploads the reusable state tree and submits `state.apply` directly to the selected target group with `test=True`. RaaS returns a JID, which SCC monitors and renders per target.

Customer `values.yaml` content is passed as execution-scoped pillar data. It is not uploaded to the RaaS file server and no persistent saved job is created. Use `--save-job` only when a reusable RaaS job is explicitly required; that saved job is pinned to `test=False` and contains no customer values - it applies for real every time it's run via `scc job-run`, so treat it with the same care as `--mode apply`.

### 5. Apply after Git approval

After the customer configuration change is reviewed and merged in Git, and the dry-run result is accepted:

```bash
scc deploy dns \
  --environment prod \
  --version 9.1.1 \
  --mode apply \
  --target-group vcf-prod
```

SCC refreshes the configured Git refs by default, validates the content again, displays the resolved state and values commit IDs, target group, and `test=False`, then requires explicit `apply` confirmation **before** publishing files or submitting the direct execution. For reproducible production execution, configure an approved tag or commit SHA instead of a moving branch.

## Repository layouts

Example reusable state repository:

```text
vcf-salt/
└── vcf-infra/
    ├── dns/
    │   ├── dns.sls
    │   ├── defaults.yaml
    │   ├── map.jinja
    │   └── files/
    │       └── resolv.conf.jinja
    └── ntp/
        ├── ntp.sls
        ├── defaults.yaml
        └── map.jinja
```

Example private customer-values repository:

```text
customer-values/
├── prod/
│   ├── 9.1.1/
│   │   ├── cluster-drs/
│   │   │   └── values.yaml
│   │   └── cluster-ha/
│   │       └── values.yaml
│   └── 9.1.2/
│       └── cluster-drs/
│           └── values.yaml
└── staging/
    └── 9.1.1/
        └── cluster-drs/
            └── values.yaml
```

The preferred values-source layout is:

```text
{environment}/{version}/{resource}/values.yaml
```

Other supported placeholders are `{resource}`, `{environment}`, `{version}`, and `{values}`. An explicit file can be selected with `--values-path` (`--data-path` remains a compatibility alias).

## RaaS publication and execution model

SCC publishes only the reusable state directory from the open-source repository. For example:

```text
Git:  saltext-vcf/vcf-infra/cluster-drs/
RaaS: /vcf-infra/cluster-drs/
```

The customer `values.yaml` file stays in the customer repository. During dry-run or apply SCC parses it and passes the resulting mapping as runtime pillar in the direct `state.apply` request. Every execution creates a normal RaaS runtime job/JID for monitoring, but not a persistent saved-job definition.

```text
values.yaml ──> execution-scoped pillar ──> state.apply ──> target group ──> JID/results
```

Optional reusable job creation is explicit:

```bash
scc deploy cluster-drs \
  --environment prod \
  --version 9.1.1 \
  --mode dry-run \
  --target-group prod-vcenters \
  --save-job
```

The saved job contains only the state reference, Salt environment, target group, and `test=True`. It never contains customer values.

## Static KB-to-Salt solution catalog

KB mappings are maintained in the reusable `saltext-vcf` repository beside the existing resource states. The mapping is static, Git-reviewed, and read-only at runtime. SCC and the Config AI Agent never generate a KB-to-SLS relationship.

The existing state layout stays unchanged:

```text
saltext-vcf/
├── vcf-infra/
│   ├── dns/
│   │   ├── dns.sls
│   │   ├── default.yaml
│   │   └── map.jinja
│   └── ntp/
│       ├── ntp.sls
│       ├── default.yaml
│       └── map.jinja
└── solutions/
    ├── catalog.yaml
    ├── schemas/
    │   ├── dns-values.schema.yaml
    │   └── ntp-values.schema.yaml
    ├── kb-<id>/
    │   └── solution.yaml
    └── kb-<id>/
        └── solution.yaml
```

Each `solution.yaml` maps one KB to one existing resource state:

```yaml
execution:
  state: vcf-infra.dns.dns
  description: Apply approved DNS configuration.
  values_schema: solutions/schemas/dns-values.schema.yaml
  dry_run_supported: true
```

SCC derives the resource (`dns`) and SLS (`dns.sls`) from the dotted state. Optional `resource` and `entrypoint` overrides are available only for repositories that do not follow the standard folder/file convention.

```bash
scc kb list
scc kb search "DNS lookup failed" --component "NSX Manager" --version 9.1.1
scc kb show <kb-id>
scc kb validate
scc kb plan <kb-id> --environment prod --version 9.1.1
scc kb execute <kb-id> --environment prod --version 9.1.1 --target-group prod-nsx --mode dry-run
```

For apply, SCC requires an applicable validated/verified catalog entry and explicit confirmation:

```bash
scc kb execute <kb-id>   --environment prod   --version 9.1.1   --target-group prod-nsx   --mode apply
```

Only the reusable state folder is published to the RaaS file server. Customer `values.yaml` remains in the private repository and is passed as execution-scoped pillar. KB execution uses one direct runtime RaaS job/JID and does not create a persistent saved job.

The Config AI Agent can use the same read-only contract through JSON:

```bash
scc kb search "time synchronization failed" --json
scc kb show <kb-id> --json
```

Bundled fictional DNS/NTP examples are available for authoring and UX testing:

```bash
scc kb list --demo
scc kb validate --demo
scc kb scaffold ./kb-catalog-example
```

The demo IDs and URLs are deliberately fictional and must not be presented as Broadcom-supported resolutions.

## Guided learning

The tutorials are network-free explanations. They print the commands but do not execute them.

```bash
scc tutorial
scc tutorial dns
scc tutorial kb-search
scc tutorial gitops
scc tutorial workflow
scc tutorial kb
scc tutorial pull
scc tutorial pull-data
scc tutorial upload
scc tutorial job-create
scc tutorial job-run
```

The two recommended first-time customer journeys are:

```bash
# Add the saltext-vcf and customer-values repositories, then deploy DNS
scc tutorial dns --non-interactive

# Search a static KB mapping and execute the mapped DNS state safely
scc tutorial kb-search --non-interactive
```

These tutorials do not make network calls. The complete written journeys are in
[`docs/CUSTOMER_JOURNEYS.md`](docs/CUSTOMER_JOURNEYS.md).

Useful discovery commands:

```bash
scc
scc commands
scc search git
scc examples --topic git
scc help deploy
scc workflow
```

## Git source management

```bash
scc repo setup
scc repo add <name> --kind states|data --url <url>
scc repo list
scc repo show <name>
scc repo use <name>
scc repo test <name>
scc repo test --all
scc repo sync --all
scc repo login <name>
scc repo logout <name>
scc repo export --output repositories.yaml
scc repo import repositories.yaml
scc repo remove <name>
scc repo path
```

`repo export` and `repo import` contain non-secret metadata only, making them suitable for onboarding and review.

The older `scc configure-git`, `scc pull`, and `scc pull-data` commands remain available for compatibility and advanced/manual operation. They now use the same generic Git/cache service; they are no longer GitHub raw-file implementations. New users should normally start with `scc repo setup` and `scc deploy`.

## Low-level operations

SCC does not remove access to individual RaaS steps:

```bash
# Browse
scc list --type minions
scc fs-list --env base
scc target-group-list
scc pillar-list
scc job-list

# Read-only Salt execution
scc exec test.ping --target '*'
scc exec grains.get --target '<minion>' --arg os

# Manual file-server operation
scc upload ./states/cluster-drs --path /vcf-infra/cluster-drs --env base
scc download /dns --output ./downloaded --env base --recursive

# Manual state operation; test mode is the default
scc run /vcf-infra/cluster-drs/cluster-drs.sls --target-group vcf-prod --env base --test
scc run /vcf-infra/cluster-drs/cluster-drs.sls --target-group vcf-prod --env base --no-test
```

Potentially mutating commands require explicit confirmation. State execution defaults to `test=True`.

## Connection profiles

```bash
scc configure --name lab
scc profile login lab
scc profile list
scc profile show lab
scc profile use lab
scc profile test lab
scc --profile production status
```

Environment selection is also supported:

```bash
export SCC_PROFILE=production
scc status
```

## Themes and plain mode

```bash
scc theme list
scc theme preview --all
scc theme use enterprise
scc theme disable       # persistent plain terminal mode
scc theme enable ocean
scc --theme plain status
```

Available themes include `ocean`, `enterprise`, `graphite`, `forest`, `amber`, `high-contrast`, and `plain`. JSON and YAML output remain undecorated regardless of theme.

## Configuration files and secrets

By default:

```text
~/.scc/config.yaml          # non-secret RaaS profiles and global UX settings
~/.scc/repositories.yaml    # non-secret Git source metadata
~/.cache/salt-config-cli/   # private shallow Git cache and session data
.scc/work/                  # validated local deployment workspaces
```

Credentials are resolved separately from:

- OS keychain;
- SSH agent / Git credential helper;
- source-specific environment variables;
- stdin, a protected file, or masked prompt when explicitly requested.

Legacy `git_*` fields in an older connection file are read only for migration into `repositories.yaml`. New commands do not write Git metadata into the RaaS profile file.

## Automation

Use explicit structured output where available:

```bash
scc repo list --json
scc deploy dns --environment prod --version 9.1.1 --mode plan
scc exec test.ping --target '*' --output json
```

Useful environment variables:

```text
SCC_PROFILE
SCC_CONFIG
SCC_REPOSITORIES_CONFIG
SCC_THEME
SCC_CACHE_DIR
SCC_GIT_TIMEOUT
SCC_GIT_TOKEN_<SOURCE_NAME>
```

For production pipelines, pin repository sources to an approved tag or commit SHA and retain the SCC execution output or RaaS job/JID with the change record.

## Development

```bash
python3 -m pip install -e '.[dev]'
pytest -q
ruff check .
python -m compileall -q salt_config_cli
python scripts/check_release.py
python -m build
```

See:

- [`docs/GITOPS_WORKFLOW.md`](docs/GITOPS_WORKFLOW.md)
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/SAFETY_MODEL.md`](docs/SAFETY_MODEL.md)
- [`docs/RAAS_COMPATIBILITY.md`](docs/RAAS_COMPATIBILITY.md)
- [`SECURITY.md`](SECURITY.md)

## Open-source contribution

Contributions are welcome. Keep command behavior backward compatible where practical, keep secrets out of examples and tests, and add tests for new safety or RPC behavior. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
