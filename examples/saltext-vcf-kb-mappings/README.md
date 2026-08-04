# saltext-vcf KB mappings

Copy the `solutions` directory into the root of `saltext-vcf`.

## Included mappings

- **304611** — searchable, review required, execution disabled.
- **317825** — verified search metadata, manual-only resolution.
- **317537** — verified mapping to `vcf-infra.ntp.ntp`; supports plan, dry-run, and apply.

The fail-closed entries deliberately do not invent an SLS mapping.

## Validate

```bash
python tools/validate_catalog.py
scc kb validate
scc kb list
scc kb search 304611
scc kb search "duplicate DNS records"
scc kb search "ESXi NTP"
scc kb show 317537
```

## NTP customer values example

```yaml
ntp:
  servers:
    - ntp1.example.com
    - ntp2.example.com
  service_enabled: true
  service_policy: on
```

Customer `values.yaml` is passed as execution-scoped pillar and is not stored on the RaaS file server.
