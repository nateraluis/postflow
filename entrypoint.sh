#!/bin/bash
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start cron
echo "Starting cron service..."
cron

# Optional: Tail the log so it's visible in Docker logs
touch /var/log/cron.log
tail -f /var/log/cron.log &

echo "Starting server..."
exec "$@"
