# KB Solution Catalog

## Purpose

The solution catalog is the static, authoritative mapping between a published KB resolution and one existing reusable Salt state. The Config AI Agent may search and execute catalog entries, but it must never infer, generate, or modify a KB-to-SLS mapping.

## Ownership boundary

```text
saltext-vcf pull request
  ├── existing resource SLS
  ├── solution.yaml mapping
  ├── optional values schema
  ├── applicability and risk metadata
  └── tests
          ↓ reviewed merge
static released catalog
          ↓ read-only lookup
Config AI Agent / SCC
          ↓ runtime context
VCF inventory + customer values + target group
          ↓ direct execution
RaaS JID and results
```

Static catalog data includes the KB ID/title, supported versions/components, symptoms, one mapped state, risk, verification status, and optional values-schema path.

Dynamic runtime data includes the customer prompt, VCF inventory/version, affected component, target group, customer `values.yaml`, Git commits, dry-run results, and RaaS JID.

## Repository layout

```text
saltext-vcf/
├── vcf-infra/
│   └── dns/
│       ├── dns.sls
│       ├── default.yaml
│       └── map.jinja
└── solutions/
    ├── catalog.yaml
    ├── schemas/
    │   └── dns-values.schema.yaml
    └── kb-123456/
        └── solution.yaml
```

`solutions/catalog.yaml` is the compact search index. `solutions/<solution-id>/solution.yaml` is the authoritative mapping.

## Simple solution definition

```yaml
api_version: saltext.vcf/v1
kind: KBResolution

metadata:
  id: kb-123456
  title: DNS mismatch affects component connectivity
  status: verified
  maturity: production

kb:
  provider: broadcom
  id: "123456"

applicability:
  products: [VCF]
  components: [NSX Manager, SDDC Manager]
  versions: [9.1.x]

execution:
  state: vcf-infra.dns.dns
  description: Apply approved DNS configuration.
  values_schema: solutions/schemas/dns-values.schema.yaml
  dry_run_supported: true

risk:
  level: medium
  requires_confirmation: true
```

SCC derives `dns` and `dns.sls` from `vcf-infra.dns.dns`. This keeps catalog authoring small and preserves the original state folder structure.

## Authoring rules

1. Reuse the existing product-oriented SLS; do not create `validate.sls`, `configure.sls`, or `kb-123456.sls` just for the catalog.
2. Keep each KB mapping to one existing resource state.
3. Do not copy full KB article text into the repository. Store the canonical ID/link, concise summary, symptoms, applicability, and state mapping.
4. Use `validated` or `verified` only after tests and review.
5. Keep customer IPs, hostnames, credentials, and instance data out of the open-source repository.
6. Customer data is selected from `<environment>/<version>/<resource>/values.yaml` and passed only as runtime pillar.

## CLI contract

```bash
scc kb search "NSX Manager disconnected"
scc kb show <kb-id>
scc kb validate
scc kb plan <kb-id> --environment prod --version 9.1.1
scc kb execute <kb-id> --environment prod --version 9.1.1 --target-group prod-nsx --mode dry-run
```

`plan` is local and no-change. Dry-run publishes the reviewed resource folder and executes the mapped state with `test=True`. Apply confirms once and executes the same mapped state with `test=False`.

## Agent contract

The agent must:

- execute only the single state referenced by the selected catalog entry;
- reject unsupported component/version combinations;
- prefer validated or verified entries;
- disclose status and risk;
- default to dry-run;
- require confirmation before apply;
- return catalog version, catalog Git commit, solution ID, state/value commits, target group, and RaaS JID.

When no mapping exists, the agent reports that no cataloged automation is available. It does not substitute a semantically similar state.

## Fictional examples

The source tree contains `examples/kb_catalog` and the installed CLI provides `scc kb scaffold`. DNS/NTP IDs use the `DEMO-*` namespace and `example.invalid` URLs so they cannot be confused with real Broadcom support content.
