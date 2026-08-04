{# Example only. Replace this test state with a reviewed, component-specific state. #}
{% set desired = salt['cp.get_file_str']('salt://fleet_settings/data/ntp.yaml', saltenv=saltenv) %}
validate_ntp_desired_state:
  test.configurable_test_state:
    - name: NTP desired-state payload is available
    - changes: false
    - result: true
    - comment: {{ ('Loaded NTP desired-state content (' ~ (desired | length) ~ ' bytes)') | json }}
