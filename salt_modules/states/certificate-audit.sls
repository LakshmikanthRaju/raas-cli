# Certificate Audit State
# Discovers all SSL/TLS certificates and reports expiration status
#
# Usage:
#   scc run /certificate-audit.sls --target-group ops --test --env vcfsecops
#   scc run /certificate-audit.sls --target-group ops --env vcfsecops
#
# This state finds certificates in common locations and reports:
#   - Certificate path
#   - Subject
#   - Expiration date and days remaining
#   - Status (OK, EXPIRING SOON, EXPIRED)

# Find all certificates and check expiration
certificate_audit:
  cmd.run:
    - name: |
        echo "=== Certificate Audit Report ==="
        echo "Hostname: $(hostname)"
        echo "Date: $(date)"
        echo ""
        
        # Common certificate locations
        CERT_PATHS="/etc/ssl/certs /etc/pki/tls/certs /etc/vmware/ssl /var/lib/vmware /opt/vmware /etc/ssl/private"
        
        FOUND=0
        EXPIRING=0
        EXPIRED=0
        
        for dir in $CERT_PATHS; do
          if [ -d "$dir" ]; then
            find "$dir" -type f \( -name "*.crt" -o -name "*.pem" -o -name "*.cer" \) 2>/dev/null | while read cert; do
              if openssl x509 -in "$cert" -noout 2>/dev/null; then
                EXPIRY=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | cut -d= -f2)
                SUBJECT=$(openssl x509 -in "$cert" -noout -subject 2>/dev/null | sed 's/subject=//' | head -c 60)
                
                # Calculate days left (works on both Linux and BSD/macOS)
                EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$EXPIRY" +%s 2>/dev/null)
                NOW_EPOCH=$(date +%s)
                DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))
                
                if [ "$DAYS_LEFT" -lt 0 ]; then
                  STATUS="EXPIRED"
                  ICON="[CRITICAL]"
                elif [ "$DAYS_LEFT" -lt 30 ]; then
                  STATUS="EXPIRING_SOON"
                  ICON="[WARNING]"
                elif [ "$DAYS_LEFT" -lt 90 ]; then
                  STATUS="EXPIRING"
                  ICON="[NOTICE]"
                else
                  STATUS="OK"
                  ICON="[OK]"
                fi
                
                echo "$ICON $cert"
                echo "    Subject: $SUBJECT"
                echo "    Expires: $EXPIRY (${DAYS_LEFT} days remaining)"
                echo "    Status: $STATUS"
                echo ""
              fi
            done
          fi
        done
        
        echo "=== End of Certificate Audit ==="
    - shell: /bin/bash
