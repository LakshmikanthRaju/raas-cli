# VCF Version Check State
#
# This state file calls the vcf_version module to collect version information
# from VCF components and reports the results.
#
# Prerequisites:
#   1. Upload the vcf_version module: scc upload-module vcf_version.py
#   2. Upload credentials pillar: scc upload-pillar vcf_credentials.yaml
#   3. Sync modules: scc exec saltutil.sync_modules
#   4. Refresh pillar: scc exec saltutil.refresh_pillar
#
# Usage:
#   scc upload states/vcf_version_check.sls --path /vcf_version_check.sls
#   scc run /vcf_version_check.sls --target "*"
#   scc run /vcf_version_check.sls --target "vcfops_resource_kind:nsx" --target-type grain

# Get version based on minion's vcfops_resource_kind grain
get_vcf_version:
  module.run:
    - name: vcf_version.get_version

# Report version info as a test state (visible in output)
report_version:
  test.show_notification:
    - text: |
        VCF Component Version Report
        ============================
        Minion: {{ grains['id'] }}
        Resource Kind: {{ grains.get('vcfops_resource_kind', 'unknown') }}
        OS: {{ grains.get('os', 'unknown') }}
