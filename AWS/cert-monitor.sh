#!/bin/bash
# Certificate expiration monitoring script
# This script checks if the SSL certificate is expiring soon and logs warnings

set -e

DOMAIN="postflow.photo"
WARNING_DAYS=14  # Warn if cert expires in less than 14 days
LOG_FILE="/home/ubuntu/logs/cert-monitor.log"

# Get certificate expiration date
EXPIRY_DATE=$(echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | openssl x509 -noout -enddate | cut -d= -f2)

# Convert to epoch time
EXPIRY_EPOCH=$(date -d "$EXPIRY_DATE" +%s)
CURRENT_EPOCH=$(date +%s)

# Calculate days until expiration
DAYS_UNTIL_EXPIRY=$(( ($EXPIRY_EPOCH - $CURRENT_EPOCH) / 86400 ))

# Log the result
echo "[$(date)] Certificate for $DOMAIN expires in $DAYS_UNTIL_EXPIRY days (on $EXPIRY_DATE)" | tee -a "$LOG_FILE"

# Check if certificate is expired or expiring soon
if [ $DAYS_UNTIL_EXPIRY -lt 0 ]; then
    echo "[$(date)] ERROR: Certificate for $DOMAIN has EXPIRED!" | tee -a "$LOG_FILE"
    exit 1
elif [ $DAYS_UNTIL_EXPIRY -lt $WARNING_DAYS ]; then
    echo "[$(date)] WARNING: Certificate for $DOMAIN expires in $DAYS_UNTIL_EXPIRY days!" | tee -a "$LOG_FILE"
    exit 2
else
    echo "[$(date)] Certificate status: OK" | tee -a "$LOG_FILE"
    exit 0
fi
