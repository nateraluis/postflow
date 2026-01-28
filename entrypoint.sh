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

# Start Django tasks database worker in background
echo "Starting Django tasks database worker..."
python manage.py run_db_worker &
DB_WORKER_PID=$!
echo "Database worker started with PID $DB_WORKER_PID"

# Trap SIGTERM and SIGINT to gracefully shutdown background processes
cleanup() {
    echo 'Stopping background processes...'
    kill -TERM $SCHEDULER_PID 2>/dev/null || true
    kill -TERM $DB_WORKER_PID 2>/dev/null || true
    wait $SCHEDULER_PID 2>/dev/null || true
    wait $DB_WORKER_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "Starting server..."
exec "$@"
