{# Example only. Replace this test state with a reviewed, component-specific state. #}
{% set desired = salt['cp.get_file_str']('salt://fleet_settings/data/dns.yaml', saltenv=saltenv) %}
validate_dns_desired_state:
  test.configurable_test_state:
    - name: DNS desired-state payload is available
    - changes: false
    - result: true
    - comment: {{ ('Loaded DNS desired-state content (' ~ (desired | length) ~ ' bytes)') | json }}
