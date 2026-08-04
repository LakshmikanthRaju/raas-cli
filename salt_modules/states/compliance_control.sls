# Salt state file for execute compliance controls with the given configuration and overrides

# required grains
{% set compliance_config = "compliance_config" %}

{% set product_category = salt['grains.get']('product') %}
{% set minion_id = salt['grains.get']('id') %}

# global import section - required
{% from 'conf/global.jinja' import global with context %}

{% set control_config = global[compliance_config] %}

# region overrides section
{% from 'conf/region-us-west-2.jinja' import region with context %}
  # this merges the global with the region overrides and based on the merge_lists=True flag, the merge is a union for list items
{% set control_config = salt['defaults.merge'](control_config, region[compliance_config], merge_lists=True) %}

# deployment overrides section
{% from 'conf/deployment-overrides.jinja' import deployment with context %}
{% set vcf_id = "vcfid." + salt['grains.get']('vcf_id') %}
{% if vcf_id in deployment %}
  {% set deployment_overrides = deployment[vcf_id] %}
  {% set control_config = salt['defaults.merge'](control_config, deployment_overrides[compliance_config], merge_lists=True) %}
{% endif %}

# instance overrides section
{% from 'conf/instance-overrides.jinja' import instance with context %}
{% if minion_id in instance %}
  {% set instance_overrides = instance[minion_id] %}
  {% set control_config = salt['defaults.merge'](control_config, instance_overrides[compliance_config], merge_lists=True) %}
{% endif %}

{% set target_control_config = {"compliance_config" : control_config } %}

compliance_controls:
  vmware_compliance_control.check_control:
    - control_config: {{target_control_config}}
    - product: {{product_category}}

