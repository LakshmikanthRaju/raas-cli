# DNS Reachability Check State
# Pings configured DNS servers and verifies DNS resolution
#
# Usage:
#   scc run /dns-reachability.sls --target-group ops --test --env vcfsecops
#   scc run /dns-reachability.sls --target-group ops --env vcfsecops
#
# Pillar options:
#   dns_servers:          # List of DNS servers to check (optional, reads from resolv.conf if not set)
#     - 192.0.2.53
#     - 192.0.2.54
#   dns_test_domains:     # Domains to test resolution against
#     - google.com
#     - vmware.com

{% set dns_servers = salt['pillar.get']('dns_servers', []) %}
{% set test_domains = salt['pillar.get']('dns_test_domains', ['google.com', 'vmware.com']) %}

# Check DNS server reachability and resolution
dns_reachability_check:
  cmd.run:
    - name: |
        echo "=== DNS Reachability Report ==="
        echo "Hostname: $(hostname)"
        echo "Date: $(date)"
        echo ""
        
        ISSUES=0
        
        # Get DNS servers from pillar or resolv.conf
        {% if dns_servers %}
        DNS_SERVERS="{{ dns_servers | join(' ') }}"
        echo "DNS Servers (from pillar): $DNS_SERVERS"
        {% else %}
        DNS_SERVERS=$(grep "^nameserver" /etc/resolv.conf 2>/dev/null | awk '{print $2}' | tr '\n' ' ')
        echo "DNS Servers (from /etc/resolv.conf): $DNS_SERVERS"
        {% endif %}
        
        echo ""
        echo "=== Current DNS Configuration ==="
        cat /etc/resolv.conf 2>/dev/null | grep -v "^#" | grep -v "^$"
        
        echo ""
        echo "=== DNS Server Ping Tests ==="
        printf "%-12s %-20s %s\n" "STATUS" "SERVER" "LATENCY"
        echo "----------------------------------------"
        
        for dns in $DNS_SERVERS; do
          if [ -n "$dns" ]; then
            PING_RESULT=$(ping -c 3 -W 2 "$dns" 2>&1)
            if echo "$PING_RESULT" | grep -q "0 received\|100% packet loss\|unreachable"; then
              printf "%-12s %-20s %s\n" "[CRITICAL]" "$dns" "UNREACHABLE"
              ISSUES=$((ISSUES + 1))
            else
              LATENCY=$(echo "$PING_RESULT" | tail -1 | awk -F'/' '{print $5}')
              if [ -n "$LATENCY" ]; then
                printf "%-12s %-20s %s ms\n" "[OK]" "$dns" "$LATENCY"
              else
                printf "%-12s %-20s %s\n" "[OK]" "$dns" "reachable"
              fi
            fi
          fi
        done
        
        echo ""
        echo "=== DNS Resolution Tests ==="
        printf "%-12s %-30s %s\n" "STATUS" "DOMAIN" "RESOLVED IP"
        echo "------------------------------------------------"
        
        TEST_DOMAINS="{{ test_domains | join(' ') }}"
        for domain in $TEST_DOMAINS; do
          # Try nslookup first, fall back to host command
          RESOLVED=$(nslookup "$domain" 2>/dev/null | grep -A1 "Name:" | tail -1 | awk '{print $2}')
          if [ -z "$RESOLVED" ]; then
            RESOLVED=$(host "$domain" 2>/dev/null | grep "has address" | head -1 | awk '{print $4}')
          fi
          if [ -z "$RESOLVED" ]; then
            RESOLVED=$(getent hosts "$domain" 2>/dev/null | head -1 | awk '{print $1}')
          fi
          
          if [ -n "$RESOLVED" ]; then
            printf "%-12s %-30s %s\n" "[OK]" "$domain" "$RESOLVED"
          else
            printf "%-12s %-30s %s\n" "[CRITICAL]" "$domain" "RESOLUTION FAILED"
            ISSUES=$((ISSUES + 1))
          fi
        done
        
        echo ""
        echo "=== Network Connectivity Summary ==="
        # Check default gateway
        GATEWAY=$(ip route 2>/dev/null | grep default | awk '{print $3}' | head -1)
        if [ -z "$GATEWAY" ]; then
          GATEWAY=$(netstat -rn 2>/dev/null | grep "^0.0.0.0" | awk '{print $2}' | head -1)
        fi
        
        if [ -n "$GATEWAY" ]; then
          if ping -c 1 -W 2 "$GATEWAY" > /dev/null 2>&1; then
            echo "Default Gateway: $GATEWAY [OK]"
          else
            echo "Default Gateway: $GATEWAY [UNREACHABLE]"
            ISSUES=$((ISSUES + 1))
          fi
        else
          echo "Default Gateway: Not found [WARNING]"
        fi
        
        echo ""
        if [ "$ISSUES" -eq 0 ]; then
          echo "=== Overall Status: OK - All DNS checks passed ==="
        else
          echo "=== Overall Status: FAILED - $ISSUES issue(s) detected ==="
          exit 1
        fi
    - shell: /bin/bash
