# VCF Version Report State
#
# Collects version information from all VCF component types and writes
# a report file on each minion.
#
# Usage:
#   scc run /vcf_version_report.sls --target "*"

{% set version_info = salt['vcf_version.get_version']() %}

version_report_dir:
  file.directory:
    - name: /var/log/vcf_version
    - makedirs: True

version_report_file:
  file.managed:
    - name: /var/log/vcf_version/version.json
    - contents: |
        {
          "minion_id": "{{ grains['id'] }}",
          "resource_kind": "{{ version_info.get('resource_kind', 'unknown') }}",
          "version": "{{ version_info.get('version', 'unknown') }}",
          "build": "{{ version_info.get('build', '') }}",
          "error": {{ version_info.get('error') | json if version_info.get('error') else 'null' }},
          "collected_at": "{{ None | strftime('%Y-%m-%dT%H:%M:%SZ') }}"
        }
    - require:
      - file: version_report_dir

report_success:
  test.succeed_with_changes:
    - comment: |
        Version collected for {{ grains['id'] }}:
        {% if version_info.get('error') %}
        ERROR: {{ version_info.get('error') }}
        {% else %}
        {{ version_info.get('resource_kind', 'unknown') }}: {{ version_info.get('version', 'unknown') }}{% if version_info.get('build') %} ({{ version_info.get('build') }}){% endif %}
        {% endif %}
    - require:
      - file: version_report_file
