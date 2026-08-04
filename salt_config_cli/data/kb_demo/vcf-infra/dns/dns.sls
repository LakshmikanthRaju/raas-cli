{% from "vcf-infra/dns/map.jinja" import dns with context %}
apply-approved-dns-values:
  test.show_notification:
    - text: "Demo only: apply DNS servers {{ dns.get('servers', []) }} and search domains {{ dns.get('search_domains', []) }}"
