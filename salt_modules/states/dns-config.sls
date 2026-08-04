# DNS Configuration State
# 
# This state manages DNS resolver configuration using Salt's native file module.
# Manages /etc/resolv.conf for DNS resolver settings.
#
# Usage:
#   scc run /dns-config.sls --target-group ops --test --env vcfsecops
#   scc run /dns-config.sls --target-group ops --env vcfsecops
#
# Pass DNS servers via pillar:
#   pillar:
#     dns_servers:
#       - 192.0.2.53
#       - 192.0.2.54
#     dns_search_domains:
#       - example.com
#       - corp.example.com

{# Get DNS servers from pillar with defaults #}
{% set dns_servers = salt['pillar.get']('dns_servers', ['192.0.2.53', '192.0.2.54']) %}
{% set dns_search_domains = salt['pillar.get']('dns_search_domains', ['localdomain']) %}
{% set dns_options = salt['pillar.get']('dns_options', ['timeout:2', 'attempts:3']) %}

# Configure DNS resolver using Salt's file.managed
dns_config:
  file.managed:
    - name: /etc/resolv.conf
    - contents: |
        # Managed by Salt - DNS Configuration
        # Generated for minion: {{ grains['id'] }}
        # Do not edit manually - changes will be overwritten
        
        # Search domains
        search {% for domain in dns_search_domains %}{{ domain }} {% endfor %}

        # DNS servers
        {% for server in dns_servers %}
        nameserver {{ server }}
        {% endfor %}
        
        # Resolver options
        {% if dns_options %}
        options {% for opt in dns_options %}{{ opt }} {% endfor %}

        {% endif %}
    - user: root
    - group: root
    - mode: '0644'
