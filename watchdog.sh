#!/bin/bash

CONTAINER_NAME="postflow_django"
LOG_FILE="/home/ubuntu/logs/watchdog.log"

# Create log directory if missing
mkdir -p /home/ubuntu/logs
touch "$LOG_FILE"

echo "[$(date)] Watchdog started for container: $CONTAINER_NAME" >> "$LOG_FILE"

while true; do
  health_status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null)

  if [ "$health_status" == "unhealthy" ]; then
    echo "[$(date)] ❌ $CONTAINER_NAME is unhealthy — restarting..." >> "$LOG_FILE"
    docker restart "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1
  else
    echo "[$(date)] ✅ $CONTAINER_NAME is healthy." >> "$LOG_FILE"
  fi

  sleep 60
done

