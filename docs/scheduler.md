# PostFlow Scheduler Documentation

## Overview

PostFlow uses **APScheduler** (Advanced Python Scheduler) to reliably process scheduled social media posts and refresh Instagram access tokens. This Python-based scheduler replaces the previous system cron implementation, providing better reliability, error handling, and integration with Django.

## Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│              Docker Container                    │
│                                                  │
│  ┌────────────────┐      ┌──────────────────┐  │
│  │  uWSGI Server  │      │   APScheduler    │  │
│  │  (Django App)  │      │   Background     │  │
│  └────────────────┘      │   Process        │  │
│                          └──────────────────┘  │
│                                 │               │
│                          ┌──────▼──────┐       │
│                          │   Jobs:      │       │
│                          │  - Post      │       │
│                          │  - Tokens    │       │
│                          └─────────────┘       │
│                                                  │
│  Lock File: /tmp/postflow_scheduler.lock       │
└─────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `postflow/scheduler.py` | Core scheduler implementation with APScheduler |
| `postflow/management/commands/run_scheduler.py` | Django management command to start scheduler |
| `postflow/cron.py` | Business logic for processing posts (unchanged) |
| `entrypoint.sh` | Docker startup script that launches scheduler |
| `dockerfile` | Container configuration (cron removed) |

## How It Works

### Scheduler Initialization

1. **Lock Acquisition**: When starting, the scheduler acquires a file lock at `/tmp/postflow_scheduler.lock` containing the process PID
2. **Stale Lock Handling**: If a lock file exists from a dead process, it's automatically cleaned up
3. **Duplicate Prevention**: Only one scheduler instance can run at a time

### Job Scheduling

The scheduler runs two jobs:

#### 1. Process Scheduled Posts
- **Frequency**: Every 1 minute
- **Function**: `postflow.cron.post_scheduled()`
- **Purpose**: Checks for pending posts with `post_date <= now` and publishes them to:
  - Pixelfed/Mastodon-compatible instances
  - Native Mastodon instances
  - Instagram Business accounts

#### 2. Refresh Instagram Tokens
- **Frequency**: Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
- **Function**: Django management command `refresh_instagram_tokens`
- **Purpose**: Refreshes Instagram Business API access tokens before they expire

### APScheduler Configuration

```python
scheduler = BackgroundScheduler(
    timezone='UTC',
    job_defaults={
        'coalesce': True,      # Combine multiple missed executions
        'max_instances': 1,     # Only one instance per job at a time
        'misfire_grace_time': 30,  # 30 seconds grace for missed jobs
    }
)
```

### Error Handling

- **Job Failures**: Errors in individual jobs are caught and logged; scheduler continues running
- **Automatic Recovery**: If a job fails, it will retry on the next scheduled execution
- **Logging**: All events logged to Django's `postflow` logger (visible in Docker logs)

### Graceful Shutdown

The scheduler handles shutdown signals properly:
- **SIGTERM/SIGINT**: Triggers graceful shutdown
- **Lock Release**: Removes lock file on exit
- **Job Completion**: Waits for running jobs to finish (with timeout)

## Deployment

### Docker Integration

The scheduler starts automatically when the Django container starts:

**entrypoint.sh:**
```bash
# Start APScheduler in background
python manage.py run_scheduler &
SCHEDULER_PID=$!

# Trap signals for graceful shutdown
trap "kill -TERM $SCHEDULER_PID; wait $SCHEDULER_PID" SIGTERM SIGINT

# Start Django server
exec uwsgi ...
```

### Health Checks

Docker Compose monitors both the scheduler and Django server:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep -f 'manage.py run_scheduler' && pgrep uwsgi"]
  interval: 30s
  timeout: 5s
  retries: 3
```

If either process dies, Docker automatically restarts the container.

## Operations

### Starting the Scheduler (Development)

```bash
# Start in foreground (blocks)
uv run manage.py run_scheduler

# Start in background
uv run manage.py run_scheduler &
```

### Checking Scheduler Status

```bash
# Check if scheduler is running
docker exec postflow_django pgrep -f "manage.py run_scheduler"

# View scheduler logs
docker-compose logs -f django | grep -i "scheduler\|postflow"

# Check lock file
docker exec postflow_django cat /tmp/postflow_scheduler.lock
```

### Viewing Scheduled Jobs

The scheduler logs all scheduled jobs at startup:

```
INFO PostFlow scheduler started successfully
INFO Scheduled 2 job(s):
INFO   - Process scheduled posts (ID: post_scheduled, Next run: 2025-01-15 10:23:00+00:00)
INFO   - Refresh Instagram access tokens (ID: refresh_instagram_tokens, Next run: 2025-01-15 12:00:00+00:00)
```

### Manual Job Execution

You can still run jobs manually for testing:

```bash
# Manually process scheduled posts
docker exec postflow_django python manage.py run_post_scheduled

# Manually refresh Instagram tokens
docker exec postflow_django python manage.py refresh_instagram_tokens
```

### Restarting the Scheduler

```bash
# Restart entire Django container (cleanest approach)
docker-compose restart django

# Or rebuild if code changed
docker-compose up --build -d django
```

## Troubleshooting

### Scheduler Not Starting

**Symptom**: Health check fails, no scheduler logs

**Solutions:**
```bash
# Check for lock file from crashed process
docker exec postflow_django ls -la /tmp/postflow_scheduler.lock
docker exec postflow_django rm /tmp/postflow_scheduler.lock

# Check entrypoint.sh logs
docker-compose logs django | grep -i "scheduler"

# Verify APScheduler is installed
docker exec postflow_django python -c "import apscheduler; print(apscheduler.__version__)"
```

### Posts Not Being Processed

**Symptom**: Pending posts remain unposted

**Debug steps:**
```bash
# Check scheduler is running
docker exec postflow_django pgrep -f "run_scheduler"

# Check for pending posts
docker exec postflow_django python manage.py shell
>>> from postflow.models import ScheduledPost
>>> from django.utils import timezone
>>> ScheduledPost.objects.filter(status='pending', post_date__lte=timezone.now()).count()

# Check logs for errors
docker-compose logs django | grep -i "error\|exception"

# Manually trigger job
docker exec postflow_django python manage.py run_post_scheduled
```

### Lock File Issues

**Symptom**: "Scheduler already running" error but no process exists

**Solution:**
```bash
# Remove stale lock file
docker exec postflow_django rm /tmp/postflow_scheduler.lock

# Restart container
docker-compose restart django
```

### Job Execution Delays

**Symptom**: Jobs run late or are skipped

**APScheduler behavior:**
- **Coalesce**: Multiple missed executions combine into one
- **Misfire Grace Time**: Jobs delayed >30 seconds are skipped
- **Max Instances**: Only one instance of each job runs at a time

**Solutions:**
- Check container resources (CPU/memory)
- Review job execution time (jobs should complete in <60 seconds)
- Check for database connection issues

## Monitoring & Logging

### Log Levels

The scheduler uses Django's `postflow` logger:

```python
LOGGING = {
    'loggers': {
        'postflow': {
            'handlers': ['console'],
            'level': 'DEBUG',  # Set to INFO in production
            'propagate': False,
        },
    },
}
```

### Important Log Messages

| Message | Meaning |
|---------|---------|
| `PostFlow scheduler started successfully` | Scheduler initialized |
| `Scheduled 2 job(s):` | Jobs registered |
| `Running post_scheduled job...` | Processing posts |
| `No pending posts to process` | No posts due |
| `Processing N pending post(s)` | Publishing posts |
| `Scheduler lock acquired` | Lock obtained successfully |
| `Scheduler already running with PID X` | Duplicate instance prevented |
| `Shutting down scheduler...` | Graceful shutdown initiated |

### Metrics to Monitor

1. **Scheduler Uptime**: Process should run continuously
2. **Job Execution Rate**:
   - `post_scheduled`: ~60 executions/hour
   - `refresh_instagram_tokens`: 4 executions/day
3. **Error Rate**: Check for exceptions in logs
4. **Post Processing Time**: Should complete within seconds
5. **Lock File Age**: Should match scheduler process age

## Testing

### Running Tests

```bash
# Run all scheduler tests
uv run pytest postflow/tests/test_scheduler.py -v

# Run specific test class
uv run pytest postflow/tests/test_scheduler.py::TestSchedulerLock -v

# Run with coverage
uv run pytest postflow/tests/test_scheduler.py --cov=postflow.scheduler
```

### Test Coverage

The test suite covers:
- ✅ Lock acquisition and release
- ✅ Stale lock detection and cleanup
- ✅ Duplicate instance prevention
- ✅ Job scheduling and execution
- ✅ Error handling in jobs
- ✅ Graceful shutdown
- ✅ Signal handling
- ✅ Full lifecycle integration

## Migration from Cron

### What Changed

| Aspect | Old (System Cron) | New (APScheduler) |
|--------|-------------------|-------------------|
| **Technology** | System cron daemon | Python APScheduler |
| **Configuration** | Crontab in Dockerfile | Python code |
| **Logging** | `/var/log/cron.log` | Django logger (stdout) |
| **Health Check** | `pgrep cron` | `pgrep -f 'run_scheduler'` |
| **Dependencies** | `cron` apt package | `apscheduler` pip package |
| **Error Handling** | Basic | Advanced with retries |
| **Lock Mechanism** | None | File-based PID lock |

### Benefits of APScheduler

1. **Reliability**: Better error handling and automatic recovery
2. **Integration**: Native Django integration, uses Django logger
3. **Debugging**: Easier to test and debug (pure Python)
4. **Flexibility**: Can dynamically add/remove jobs at runtime
5. **Monitoring**: Better visibility into job status and next run times
6. **No System Dependencies**: Removes need for cron package

## Advanced Configuration

### Adjusting Job Schedules

Edit `postflow/scheduler.py`:

```python
# Change post processing to every 30 seconds
self.scheduler.add_job(
    func=self._run_post_scheduled,
    trigger=IntervalTrigger(seconds=30),  # Changed from minutes=1
    ...
)

# Change token refresh to daily at 2 AM
self.scheduler.add_job(
    func=self._refresh_instagram_tokens,
    trigger=CronTrigger(hour=2, minute=0),  # Changed from hour='*/6'
    ...
)
```

### Adding New Jobs

```python
# In PostFlowScheduler.start() method
self.scheduler.add_job(
    func=self._your_new_job,
    trigger=IntervalTrigger(hours=1),  # Every hour
    id='your_job_id',
    name='Your Job Name',
    replace_existing=True,
)

# Add corresponding method
def _your_new_job(self):
    try:
        logger.debug("Running your job...")
        # Your job logic here
    except Exception as e:
        logger.exception(f"Error in your job: {e}")
```

### Changing Timezone

The scheduler uses UTC by default. To change:

```python
self.scheduler = BackgroundScheduler(
    timezone='America/New_York',  # Change timezone
    ...
)
```

## References

- **APScheduler Documentation**: https://apscheduler.readthedocs.io/
- **Django Management Commands**: https://docs.djangoproject.com/en/5.2/howto/custom-management-commands/
- **Docker Health Checks**: https://docs.docker.com/engine/reference/builder/#healthcheck

## Support

For issues with the scheduler:
1. Check Docker logs: `docker-compose logs django`
2. Verify health check: `docker-compose ps`
3. Review this documentation's troubleshooting section
4. Check APScheduler documentation for advanced configuration
5. Run tests: `pytest postflow/tests/test_scheduler.py`
