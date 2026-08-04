# Salt Config CLI — Customer Journeys

Salt Config CLI (`scc`) helps customers consume reusable VCF Salt states from the open-source `saltext-vcf` repository and apply customer-specific configuration from a private Git repository through RaaS.

The customer does not need to understand Salt internals such as pillar storage, file-server APIs, or RaaS RPC methods. SCC presents a simple workflow built around:

- Resources such as DNS, NTP, DRS, HA, and cluster configuration
- Environment and VCF version
- Customer `values.yaml`
- RaaS target groups
- Dry-run and apply
- KB search and mapped automation

---

## 1. Content ownership model

### Open-source `saltext-vcf` repository

The open-source repository owns the reusable implementation and the KB-to-SLS mapping.

```text
saltext-vcf/
├── vcf-infra/
│   ├── dns/
│   │   ├── dns.sls
│   │   ├── default.yaml
│   │   └── map.jinja
│   ├── ntp/
│   │   ├── ntp.sls
│   │   ├── default.yaml
│   │   └── map.jinja
│   └── cluster-drs/
│       ├── cluster-drs.sls
│       ├── default.yaml
│       └── map.jinja
│
└── solutions/
    ├── catalog.yaml
    ├── kb-123456/
    │   └── solution.yaml
    └── schemas/
        ├── solution.schema.json
        └── dns-values.schema.yaml
```

This repository contains:

- Reusable Salt states
- Default values
- Jinja mapping logic
- Templates and supporting files
- KB-to-SLS mappings
- Customer-values schemas

It must not contain customer-specific IP addresses, hostnames, credentials, or environment values.

### Customer private repository

The customer repository owns approved environment-specific configuration.

```text
customer-vcf-config/
├── dev/
│   └── 9.1.1/
│       └── dns/
│           └── values.yaml
├── staging/
│   └── 9.1.1/
│       └── dns/
│           └── values.yaml
└── prod/
    └── 9.1.1/
        ├── dns/
        │   └── values.yaml
        └── ntp/
            └── values.yaml
```

The recommended SCC layout is:

```text
{environment}/{version}/{resource}/values.yaml
```

For example:

```text
prod/9.1.1/dns/values.yaml
```

The customer uses the normal Git approval process:

```text
Update values.yaml
    ↓
Create pull request
    ↓
Review and approve
    ↓
Merge to the approved branch
    ↓
SCC pulls and executes the approved content
```

SCC does not introduce another approval manifest.

---

## 2. DNS customer values example

```yaml
dns:
  servers:
    - 10.20.10.10
    - 10.20.10.11

  search_domains:
    - prod.example.com
    - example.com

  timeout: 5
  attempts: 3
```

The exact keys must follow the contract defined by the DNS resource and its values schema in `saltext-vcf`.

---

# Customer Journey 1 — Add repositories and execute DNS configuration

## Step 1: Configure the RaaS connection

Create a named SCC connection profile:

```bash
scc configure --name production
```

Select it:

```bash
scc profile use production
```

Validate the connection:

```bash
scc status
scc doctor
```

The RaaS password or token is stored separately from the YAML configuration, using the operating-system keychain or environment variables.

---

## Step 2: Add the open-source states repository

```bash
scc repo add vcf-salt \
  --kind states \
  --url https://github.com/example/saltext-vcf.git \
  --ref v9.1.1 \
  --root vcf-infra \
  --layout "{resource}"
```

Set it as the default states source:

```bash
scc repo use vcf-salt --kind states
```

For resource `dns`, SCC resolves:

```text
Repository path: vcf-infra/dns
State file:      vcf-infra/dns/dns.sls
Salt state:      vcf-infra.dns.dns
```

---

## Step 3: Add the customer values repository

SSH example:

```bash
scc repo add customer-values \
  --kind data \
  --url ssh://git@git.example.com/customer/vcf-config.git \
  --ref main \
  --root . \
  --layout "{environment}/{version}/{resource}/values.yaml" \
  --auth ssh
```

Set it as the default values source:

```bash
scc repo use customer-values --kind data
```

SCC maps the deployment input:

```text
Resource:     dns
Environment:  prod
Version:      9.1.1

Values file:
prod/9.1.1/dns/values.yaml
```

---

## Step 4: Test repository access

```bash
scc repo test --all
```

Example result:

```text
Repository         Kind       Reference    Status
vcf-salt           States     v9.1.1       Connected
customer-values    Values     main         Connected
```

List the configured repositories:

```bash
scc repo list
```

---

## Step 5: Preview the DNS deployment

```bash
scc deploy dns \
  --environment prod \
  --version 9.1.1
```

This is a plan-only operation. It must not modify RaaS.

Example summary:

```text
DNS Deployment Plan

States source       vcf-salt
States reference    v9.1.1
States commit       a19bc42
State folder        vcf-infra/dns
State               vcf-infra.dns.dns

Values source       customer-values
Values reference    main
Values commit       82fd113
Values file         prod/9.1.1/dns/values.yaml

RaaS destination    /vcf-infra/dns
Execution           Plan only
```

SCC validates:

- `dns.sls` exists
- `default.yaml` exists
- `map.jinja` exists
- `values.yaml` is valid YAML
- Customer values match the resource schema
- Repository paths are safe
- The mapped state belongs to the same Git revision

---

## Step 6: Execute a DNS dry-run

```bash
scc deploy dns \
  --environment prod \
  --version 9.1.1 \
  --target-group prod-vcf-components \
  --mode dry-run
```

SCC performs the following workflow:

```text
Pull saltext-vcf
    ↓
Locate vcf-infra/dns
    ↓
Upload only the reusable DNS state folder to RaaS
    ↓
Pull the customer repository
    ↓
Read prod/9.1.1/dns/values.yaml
    ↓
Resolve the RaaS target group
    ↓
Execute state.apply directly with test=True
    ↓
Receive a RaaS JID
    ↓
Display results for every target
```

The direct execution is conceptually equivalent to:

```yaml
function: state.apply
state: vcf-infra.dns.dns

target:
  type: target-group
  name: prod-vcf-components

keyword_arguments:
  saltenv: vcf
  test: true
  pillar:
    dns:
      servers:
        - 10.20.10.10
        - 10.20.10.11
      search_domains:
        - prod.example.com
        - example.com
```

No persistent saved job is created by default.

---

## Step 7: Review the dry-run

Example output:

```text
DNS Dry-Run Results

Target                 Status      Proposed changes
vc-prod-01             Changes     DNS servers will be updated
nsx-prod-01            Compliant   No changes required
sddc-manager-prod      Changes     Search domain will be updated

JID                     20260801142530123456
Succeeded               3
Failed                  0
Changed                 2
Compliant               1
```

---

## Step 8: Apply the DNS configuration

```bash
scc deploy dns \
  --environment prod \
  --version 9.1.1 \
  --target-group prod-vcf-components \
  --mode apply
```

Before execution, SCC shows:

```text
Resource           dns
Environment        prod
VCF version        9.1.1
Target group       prod-vcf-components

State commit       a19bc42
Values commit      82fd113
State              vcf-infra.dns.dns
Execution          Apply configuration — test=False
```

The user must confirm the operation. SCC then submits a direct RaaS execution, receives a new JID, monitors progress, and displays the final result.

---

## RaaS file-server result

Only the reusable state implementation is uploaded:

```text
vcf-infra/
└── dns/
    ├── dns.sls
    ├── default.yaml
    └── map.jinja
```

The RaaS file server must not contain:

```text
prod/
9.1.1/
values.yaml
customer IP addresses
customer hostnames
customer credentials
```

Customer `values.yaml` is passed only as execution-scoped pillar data for the selected target group.

---

# Customer Journey 2 — Search a KB and execute the mapped state

The KB catalog is maintained in the same `saltext-vcf` repository as the state it references.

```text
saltext-vcf/
├── vcf-infra/
│   └── dns/
│       ├── dns.sls
│       ├── default.yaml
│       └── map.jinja
│
└── solutions/
    ├── catalog.yaml
    └── kb-123456/
        └── solution.yaml
```

## Example KB mapping

```yaml
api_version: saltext.vcf/v1
kind: KBResolution

metadata:
  id: kb-123456
  title: DNS configuration mismatch affects component connectivity
  status: verified

kb:
  provider: broadcom
  id: "123456"
  url: https://knowledge.broadcom.com/external/article/123456

applicability:
  products:
    - VCF
  components:
    - NSX Manager
    - vCenter
    - SDDC Manager
  versions:
    - 9.1.x

execution:
  state: vcf-infra.dns.dns
  values_schema: solutions/schemas/dns-values.schema.yaml
  dry_run_supported: true

risk:
  level: medium
  requires_confirmation: true
```

The mapping is static, version-controlled, reviewed, and read-only at runtime.

SCC and the Config AI Agent must not invent or replace the KB-to-SLS mapping.

---

## Journey A: Customer knows the KB number

Search by KB ID:

```bash
scc kb search 123456
```

Example output:

```text
KB       Title                                             Status
123456   DNS configuration mismatch affects connectivity   Verified
```

Show the mapped resolution:

```bash
scc kb show 123456
```

Example output:

```text
Broadcom KB       123456
Title             DNS configuration mismatch affects connectivity
Status            Verified
Risk              Medium

Products          VCF
Components        NSX Manager, vCenter, SDDC Manager
Versions          9.1.x

Mapped state      vcf-infra.dns.dns
Values required   DNS configuration values
Dry-run           Supported
```

---

## Journey B: Customer knows only the symptom

Search using natural operational terms:

```bash
scc kb search "NSX Manager disconnected DNS"
```

Additional examples:

```bash
scc kb search "hostname lookup failed"
scc kb search "DNS mismatch"
scc kb search "component disconnected"
```

SCC searches only the static catalog from the configured `saltext-vcf` Git revision.

---

## Step 1: Plan the KB resolution

```bash
scc kb plan 123456 \
  --environment prod \
  --version 9.1.1
```

SCC verifies:

- The KB mapping exists
- The mapping status is `verified`
- VCF `9.1.1` matches the supported version rule
- The mapped state exists in the same Git revision
- The values schema exists
- Customer `values.yaml` can be resolved

Example output:

```text
KB Resolution Plan

KB                  123456
Title               DNS configuration mismatch affects connectivity
Status              Verified
Risk                Medium

States repository   vcf-salt
Git reference       v9.1.1
Resolved commit     a19bc42

Mapped state        vcf-infra.dns.dns
State path          vcf-infra/dns/dns.sls

Values repository   customer-values
Values commit       82fd113
Values path         prod/9.1.1/dns/values.yaml

Execution           Plan only
RaaS changes        None
```

---

## Step 2: Execute the KB resolution as a dry-run

```bash
scc kb execute 123456 \
  --environment prod \
  --version 9.1.1 \
  --target-group prod-vcf-components \
  --mode dry-run
```

SCC resolves:

```text
KB 123456
    ↓
Mapped state: vcf-infra.dns.dns
    ↓
State folder: vcf-infra/dns
    ↓
Customer values: prod/9.1.1/dns/values.yaml
```

It then uses the same safe deployment engine:

```text
Publish the reusable DNS state folder
    ↓
Pass values.yaml as runtime pillar
    ↓
Execute state.apply with test=True
    ↓
Monitor the RaaS JID
    ↓
Display results
```

---

## Step 3: Apply the KB resolution

```bash
scc kb execute 123456 \
  --environment prod \
  --version 9.1.1 \
  --target-group prod-vcf-components \
  --mode apply
```

Before execution, SCC displays:

```text
KB                 123456
Mapped state       vcf-infra.dns.dns
Target group       prod-vcf-components
State commit       a19bc42
Values commit      82fd113
Execution          test=False
Risk               Medium
```

The user confirms the operation before SCC submits it to RaaS.

---

# Config AI Agent journey

A customer may ask:

> NSX Manager is disconnected in SDDC Manager and DNS lookup is failing. Is there an automated resolution?

The Config AI Agent follows this process:

```text
Understand the customer symptom
    ↓
Call solution.search
    ↓
Find the matching KB in the static saltext-vcf catalog
    ↓
Call solution.get
    ↓
Verify the mapped state
    ↓
Check VCF version and component applicability
    ↓
Present the KB and mapped Salt resolution
    ↓
Ask permission to run dry-run
    ↓
Call solution.execute with test=True
```

Example response:

```text
I found Broadcom KB 123456, which matches the DNS-related
component-disconnection symptom.

Verified Salt resolution:
  vcf-infra.dns.dns

Applicable to:
  NSX Manager, vCenter and SDDC Manager
  VCF 9.1.x

The operation supports a dry-run. Customer DNS values will be read
from prod/9.1.1/dns/values.yaml and passed only for this execution.
```

The Config AI Agent uses the catalog as the only authoritative source for KB-to-SLS mappings.

It may dynamically evaluate the customer environment, but it must not dynamically create the mapping.

---

# Direct deployment versus KB-driven deployment

```text
Direct deployment
Customer already knows the resource
    → scc deploy dns

KB-driven deployment
Customer knows the KB number or symptom
    → scc kb search / show / plan / execute
```

Both paths use the same execution engine:

```text
Reusable state from saltext-vcf
    +
Customer values from private Git
    +
Selected RaaS target group
    +
Direct state.apply
    +
test=True by default
```

---

# Safety and traceability

SCC should always report:

- RaaS profile
- States repository and resolved commit
- Customer-values repository and resolved commit
- Resource and mapped SLS
- Customer values path
- Target group
- Salt environment
- Dry-run or apply mode
- RaaS JID
- Per-target result

SCC should not:

- Store customer values on the RaaS file server
- Create persistent saved jobs by default
- Store Git credentials in repository configuration
- Generate KB-to-SLS mappings dynamically
- Execute an unverified catalog mapping without an explicit development override
- Apply changes without confirmation

---

# Quick command reference

```bash
# Configure RaaS
scc configure --name production
scc profile use production
scc doctor

# Configure Git repositories
scc repo add vcf-salt --kind states ...
scc repo add customer-values --kind data ...
scc repo use vcf-salt --kind states
scc repo use customer-values --kind data
scc repo test --all

# Direct DNS deployment
scc deploy dns --environment prod --version 9.1.1
scc deploy dns --environment prod --version 9.1.1 \
  --target-group prod-vcf-components --mode dry-run
scc deploy dns --environment prod --version 9.1.1 \
  --target-group prod-vcf-components --mode apply

# KB discovery and execution
scc kb search "DNS mismatch"
scc kb show 123456
scc kb plan 123456 --environment prod --version 9.1.1
scc kb execute 123456 --environment prod --version 9.1.1 \
  --target-group prod-vcf-components --mode dry-run
scc kb execute 123456 --environment prod --version 9.1.1 \
  --target-group prod-vcf-components --mode apply
```

---

## Summary

The complete model is:

```text
saltext-vcf
    → reusable Salt states
    → KB catalog and mappings

customer-vcf-config
    → approved environment-specific values.yaml

Salt Config CLI
    → pull
    → validate
    → publish states
    → pass runtime pillar
    → execute through RaaS
    → monitor JID
    → report results
```

This allows customers to use configuration automation directly by resource or discover it through a familiar Broadcom KB article, without requiring them to understand Salt-specific implementation details.
