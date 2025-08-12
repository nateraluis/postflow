#!/usr/bin/env sh
set -eu

while :; do
  before="$(find /etc/letsencrypt/live -type f \( -name fullchain.pem -o -name privkey.pem \) -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f1 || true)"
  certbot renew --webroot --webroot-path=/var/www/certbot --quiet || true
  after="$(find /etc/letsencrypt/live -type f \( -name fullchain.pem -o -name privkey.pem \) -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f1 || true)"

  if [ -n "$before" ] && [ -n "$after" ] && [ "$after" != "$before" ]; then
    # Reload NGINX via Docker Engine HTTP API (no docker CLI needed)
    curl --unix-socket /var/run/docker.sock -s -X POST "http://localhost/v1.41/containers/postflow_nginx/kill?signal=HUP" \
    || curl --unix-socket /var/run/docker.sock -s -X POST "http://localhost/v1.24/containers/postflow_nginx/kill?signal=HUP" \
    || true
  fi

  sleep 12h
done
