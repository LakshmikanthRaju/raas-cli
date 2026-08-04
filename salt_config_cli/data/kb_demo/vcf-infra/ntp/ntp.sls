{% from "vcf-infra/ntp/map.jinja" import ntp with context %}
apply-approved-ntp-values:
  test.show_notification:
    - text: "Demo only: apply NTP servers {{ ntp.get('servers', []) }}"
