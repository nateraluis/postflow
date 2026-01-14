#!/usr/bin/env sh
set -eu

echo "[$(date)] Certbot auto-renewer starting..."

while :; do
  echo "[$(date)] Checking for certificate renewal..."

  before="$(find /etc/letsencrypt/live -type f \( -name fullchain.pem -o -name privkey.pem \) -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f1 || true)"

  # Run certbot renewal (it only renews if cert is within 30 days of expiry)
  certbot renew --webroot --webroot-path=/var/www/certbot --quiet || echo "[$(date)] Certbot renew failed or no renewal needed"

  after="$(find /etc/letsencrypt/live -type f \( -name fullchain.pem -o -name privkey.pem \) -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f1 || true)"

  if [ -n "$before" ] && [ -n "$after" ] && [ "$after" != "$before" ]; then
    echo "[$(date)] Certificate renewed! Reloading nginx..."
    # Reload NGINX via Docker Engine HTTP API using wget (curl not available in certbot image)
    if wget --spider --method=POST --header="Content-Type: application/json" --no-check-certificate \
         --unix-socket=/var/run/docker.sock \
         "http://localhost/v1.41/containers/postflow_nginx/kill?signal=HUP" 2>/dev/null; then
      echo "[$(date)] Nginx reloaded successfully via API v1.41"
    elif wget --spider --method=POST --header="Content-Type: application/json" --no-check-certificate \
         --unix-socket=/var/run/docker.sock \
         "http://localhost/v1.24/containers/postflow_nginx/kill?signal=HUP" 2>/dev/null; then
      echo "[$(date)] Nginx reloaded successfully via API v1.24"
    else
      echo "[$(date)] ERROR: Failed to reload nginx via Docker socket"
    fi
  else
    echo "[$(date)] No certificate changes detected"
  fi

  echo "[$(date)] Sleeping for 12 hours..."
  sleep 12h
done
