# Simple Compliance Control State
#
# Runs compliance controls directly from pillar data without jinja dependencies.
# Use this when you want to pass control config via pillar file.
#
# Usage:
#   scc run /compliance_check.sls --target "vcfops_resource_kind:vcenter" -T grain --test --env vcfsecops --pillar-file salt_modules/pillars/ntp_only.yaml

{% set product_category = salt['grains.get']('product', salt['grains.get']('vcfops_resource_kind', 'vcenter')) %}
{% set compliance_config = salt['pillar.get']('compliance_config', {}) %}
{% set target_control_config = {"compliance_config": compliance_config} %}

compliance_controls:
  vmware_compliance_control.check_control:
    - control_config: {{ target_control_config | tojson | safe }}
    - product: {{ product_category }}
