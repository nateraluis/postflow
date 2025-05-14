#!/bin/bash

# Run certbot renew in Docker
docker run --rm \
  -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/certbot/www:/var/www/certbot" \
  certbot/certbot renew --webroot --webroot-path=/var/www/certbot

# Reload NGINX if any certs were renewed
docker-compose exec nginx nginx -s reload

