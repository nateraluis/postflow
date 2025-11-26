#!/bin/bash
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start APScheduler in background
echo "Starting APScheduler..."
python manage.py run_scheduler &
SCHEDULER_PID=$!
echo "Scheduler started with PID $SCHEDULER_PID"

# Trap SIGTERM and SIGINT to gracefully shutdown scheduler
trap "echo 'Stopping scheduler...'; kill -TERM $SCHEDULER_PID 2>/dev/null; wait $SCHEDULER_PID; exit 0" SIGTERM SIGINT

echo "Starting server..."
exec "$@"
