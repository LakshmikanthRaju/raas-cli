# Fictional KB Catalog Examples

These DNS and NTP mappings demonstrate the expected `saltext-vcf` structure. They are not Broadcom KB articles and must not be treated as supported fixes.

Each resource keeps the normal three-file layout:

```text
vcf-infra/<resource>/
├── <resource>.sls
├── default.yaml
└── map.jinja
```

Each reviewed `solution.yaml` maps a KB directly to that existing SLS. Customer-specific configuration remains in a separate private repository as `<environment>/<version>/<resource>/values.yaml` and is passed at execution as runtime pillar. It is never copied to the RaaS file server.
