#!/usr/bin/env sh
set -eu

echo "[$(date)] Certbot auto-renewer starting..."

reload_nginx() {
  echo "[$(date)] Certificate renewed! Reloading nginx..."
  if curl -sf --unix-socket /var/run/docker.sock \
       -X POST "http://localhost/v1.41/containers/postflow_nginx/kill?signal=HUP" >/dev/null 2>&1; then
    echo "[$(date)] Nginx reloaded successfully"
  else
    echo "[$(date)] ERROR: Failed to reload nginx via Docker socket"
  fi
}

while :; do
  echo "[$(date)] Checking for certificate renewal..."

  # Run certbot renewal with a deploy hook that touches a marker file on success
  rm -f /tmp/cert_renewed
  certbot renew --webroot --webroot-path=/var/www/certbot \
    --deploy-hook "touch /tmp/cert_renewed" \
    --quiet || echo "[$(date)] Certbot renew exited with error"

  if [ -f /tmp/cert_renewed ]; then
    reload_nginx
    rm -f /tmp/cert_renewed
  else
    echo "[$(date)] No certificate renewal needed"
  fi

  echo "[$(date)] Sleeping for 12 hours..."
  sleep 12h
done
