# NTP Configuration State
# 
# This state manages NTP configuration using Salt's native file module.
# Stores config in /etc/salt/ntp.conf to avoid permission issues.
#
# Usage:
#   scc run /ntp-config.sls --target-group ops --test --env vcfsecops
#   scc run /ntp-config.sls --target-group ops --env vcfsecops
#
# Pass NTP server via pillar:
#   pillar:
#     ntp_server: 192.0.2.10

{# Get NTP server from pillar #}
{% set ntp_server = salt['pillar.get']('ntp_server', '192.0.2.10') %}

# Ensure /etc/salt directory exists
salt_config_dir:
  file.directory:
    - name: /etc/salt
    - makedirs: True

# Configure NTP using Salt's file.managed
ntp_config:
  file.managed:
    - name: /etc/salt/ntp.conf
    - contents: |
        # Managed by Salt - NTP Configuration
        # Generated for minion: {{ grains['id'] }}
        disable auth
        server {{ ntp_server }} iburst prefer
        restrict -4 default kod notrap nomodify nopeer noquery
        restrict -6 default kod notrap nomodify nopeer noquery
        restrict 127.0.0.1
        restrict ::1
        driftfile /var/lib/ntp/drift/ntp.drift
    - user: salt
    - group: salt
    - mode: '0644'
    - require:
      - file: salt_config_dir
