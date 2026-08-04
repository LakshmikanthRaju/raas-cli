# Disk Space Audit State
# Checks log partition free space and alerts on low disk conditions
#
# Usage:
#   scc run /disk-space-audit.sls --target-group ops --test --env vcfsecops
#   scc run /disk-space-audit.sls --target-group ops --env vcfsecops
#
# Pillar options:
#   disk_warning_threshold: 80   # Percent used to trigger warning
#   disk_critical_threshold: 90  # Percent used to trigger critical

{% set warning_threshold = salt['pillar.get']('disk_warning_threshold', 80) %}
{% set critical_threshold = salt['pillar.get']('disk_critical_threshold', 90) %}

# Check disk space on log-related partitions
disk_space_audit:
  cmd.run:
    - name: |
        echo "=== Disk Space Audit Report ==="
        echo "Hostname: $(hostname)"
        echo "Date: $(date)"
        echo "Warning Threshold: {{ warning_threshold }}%"
        echo "Critical Threshold: {{ critical_threshold }}%"
        echo ""
        
        # Partitions commonly used for logs
        LOG_PARTITIONS="/var/log /var /tmp /opt/vmware/log /storage/log /var/lib"
        
        echo "=== Log Partition Status ==="
        printf "%-10s %-40s %s\n" "STATUS" "FILESYSTEM" "USAGE"
        echo "--------------------------------------------------------------"
        
        ISSUES=0
        
        for mount in $LOG_PARTITIONS; do
          if [ -d "$mount" ]; then
            LINE=$(df -h "$mount" 2>/dev/null | tail -1)
            USED_PCT=$(echo "$LINE" | awk '{print $5}' | tr -d '%')
            FILESYSTEM=$(echo "$LINE" | awk '{print $1}')
            MOUNT_PT=$(echo "$LINE" | awk '{print $6}')
            SIZE=$(echo "$LINE" | awk '{print $2}')
            USED=$(echo "$LINE" | awk '{print $3}')
            AVAIL=$(echo "$LINE" | awk '{print $4}')
            
            if [ -n "$USED_PCT" ] && [ "$USED_PCT" -eq "$USED_PCT" ] 2>/dev/null; then
              if [ "$USED_PCT" -ge {{ critical_threshold }} ]; then
                STATUS="[CRITICAL]"
                ISSUES=$((ISSUES + 1))
              elif [ "$USED_PCT" -ge {{ warning_threshold }} ]; then
                STATUS="[WARNING]"
                ISSUES=$((ISSUES + 1))
              else
                STATUS="[OK]"
              fi
              printf "%-10s %-40s %s%% (%s/%s)\n" "$STATUS" "$MOUNT_PT" "$USED_PCT" "$USED" "$SIZE"
            fi
          fi
        done
        
        echo ""
        echo "=== All Mounted Filesystems ==="
        df -h | grep -v "tmpfs\|devtmpfs\|overlay" | head -20
        
        echo ""
        echo "=== Large Log Files (>100MB) ==="
        LARGE_FILES=$(find /var/log -type f -size +100M 2>/dev/null)
        if [ -n "$LARGE_FILES" ]; then
          echo "$LARGE_FILES" | while read f; do
            SIZE=$(ls -lh "$f" 2>/dev/null | awk '{print $5}')
            echo "  $SIZE  $f"
          done
        else
          echo "  None found"
        fi
        
        echo ""
        if [ "$ISSUES" -eq 0 ]; then
          echo "=== Overall Status: OK - All partitions within thresholds ==="
        else
          echo "=== Overall Status: $ISSUES partition(s) exceeding thresholds ==="
        fi
    - shell: /bin/bash
