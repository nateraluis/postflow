# PostFlow Background Processes Documentation

## Overview

PostFlow uses two background processes for reliable task execution:

1. **APScheduler** - Processes scheduled social media posts and refreshes Instagram tokens
2. **Django Tasks Worker** - Handles background analytics tasks (engagement fetching, post syncing)

Both processes run continuously in the background and are automatically started on container deployment.

## Architecture

### Components

```
┌───────────────────────────────────────────────────────────────┐
│                      Docker Container                          │
│                                                                │
│  ┌────────────────┐   ┌──────────────────┐   ┌─────────────┐ │
│  │  uWSGI Server  │   │   APScheduler    │   │  DB Worker  │ │
│  │  (Django App)  │   │   Background     │   │  (Django    │ │
│  └────────────────┘   │   Process        │   │   Tasks)    │ │
│                       └──────────────────┘   └─────────────┘ │
│                              │                      │          │
│                       ┌──────▼──────┐        ┌─────▼──────┐  │
│                       │   Jobs:      │        │   Tasks:    │  │
│                       │  - Post      │        │  - Analytics│  │
│                       │  - Tokens    │        │  - Syncing  │  │
│                       └─────────────┘        └────────────┘  │
│                                                                │
│  Lock File: /tmp/postflow_scheduler.lock                     │
└───────────────────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `postflow/scheduler.py` | Core scheduler implementation with APScheduler |
| `postflow/management/commands/run_scheduler.py` | Django management command to start scheduler |
| `analytics_pixelfed/management/commands/run_db_worker.py` | Django management command to start tasks worker |
| `postflow/cron.py` | Business logic for processing posts (unchanged) |
| `analytics_pixelfed/tasks.py` | Background tasks for analytics (engagement, syncing) |
| `entrypoint.sh` | Docker startup script that launches both background processes |
| `dockerfile` | Container configuration |

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

#### 3. Sync Pixelfed Posts
- **Frequency**: Every hour at :15 (00:15, 01:15, 02:15, ... UTC)
- **Function**: Enqueues `sync_all_pixelfed_posts` Django task
- **Purpose**: Syncs recent posts from all connected Pixelfed accounts

#### 4. Fetch Pixelfed Engagement
- **Frequency**: Every hour at :45 (00:45, 01:45, 02:45, ... UTC)
- **Function**: Enqueues `fetch_all_pixelfed_engagement` Django task
- **Purpose**: Fetches likes, comments, and shares for Pixelfed posts

### Django Tasks Worker

The Django Tasks worker processes background tasks from the database queue:

#### Background Tasks
1. **Fetch Account Engagement** (`fetch_account_engagement`)
   - **Trigger**: Manual via dashboard "Fetch Engagement" button
   - **Function**: Fetches likes, comments, and shares for a specific account's recent posts
   - **Priority**: 10 (high priority)
   - **Queue**: default

2. **Fetch All Pixelfed Engagement** (`fetch_all_pixelfed_engagement`)
   - **Trigger**: Scheduled hourly by APScheduler (every hour at :45)
   - **Function**: Fetches engagement for all connected Pixelfed accounts
   - **Priority**: 5
   - **Queue**: default

3. **Sync All Pixelfed Posts** (`sync_all_pixelfed_posts`)
   - **Trigger**: Scheduled hourly by APScheduler (every hour at :15)
   - **Function**: Syncs recent posts from all Pixelfed accounts
   - **Priority**: 5
   - **Queue**: default

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

Both background processes start automatically when the Django container starts:

**entrypoint.sh:**
```bash
# Start APScheduler in background
python manage.py run_scheduler &
SCHEDULER_PID=$!

# Start Django tasks database worker in background
python manage.py run_db_worker &
DB_WORKER_PID=$!

# Trap signals for graceful shutdown
cleanup() {
    kill -TERM $SCHEDULER_PID 2>/dev/null || true
    kill -TERM $DB_WORKER_PID 2>/dev/null || true
    wait $SCHEDULER_PID 2>/dev/null || true
    wait $DB_WORKER_PID 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# Start Django server
exec uwsgi ...
```

### Health Checks

Docker Compose monitors all three critical processes:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep -f 'manage.py run_scheduler' && pgrep -f 'manage.py db_worker' && pgrep uwsgi"]
  interval: 30s
  timeout: 5s
  retries: 3
```

If any process dies, Docker automatically restarts the container.

## Operations

### Starting Background Processes (Development)

```bash
# Start scheduler in foreground (blocks)
uv run manage.py run_scheduler

# Start db_worker in foreground (blocks)
uv run manage.py run_db_worker

# Start both in background
uv run manage.py run_scheduler &
uv run manage.py run_db_worker &
```

### Checking Process Status

```bash
# Check if scheduler is running
docker exec postflow_django pgrep -f "manage.py run_scheduler"

# Check if db_worker is running
docker exec postflow_django pgrep -f "manage.py db_worker"

# View scheduler logs
docker-compose logs -f django | grep -i "scheduler\|postflow"

# View db_worker logs
docker-compose logs -f django | grep -i "db_worker\|django tasks"

# Check scheduler lock file
docker exec postflow_django cat /tmp/postflow_scheduler.lock
```

### Viewing Scheduled Jobs

The scheduler logs all scheduled jobs at startup:

```
INFO PostFlow scheduler started successfully
INFO Scheduled 4 job(s):
INFO   - Process scheduled posts (ID: post_scheduled, Next run: 2025-01-28 10:23:00+00:00)
INFO   - Refresh Instagram access tokens (ID: refresh_instagram_tokens, Next run: 2025-01-28 12:00:00+00:00)
INFO   - Sync Pixelfed posts (ID: sync_pixelfed_posts, Next run: 2025-01-28 10:15:00+00:00)
INFO   - Fetch Pixelfed engagement (ID: fetch_pixelfed_engagement, Next run: 2025-01-28 10:45:00+00:00)
```

### Viewing Background Tasks

Check task status in Django shell:

```bash
docker exec -it postflow_django python manage.py shell
```

```python
from django_tasks.models import TaskResult

# View all tasks
TaskResult.objects.all().values('id', 'status', 'task_path', 'enqueued_at')

# View pending tasks
TaskResult.objects.filter(status='pending').count()

# View completed tasks
TaskResult.objects.filter(status='complete').count()

# View failed tasks
TaskResult.objects.filter(status='failed')

# View specific task details
task = TaskResult.objects.get(id='c31d5827-4760-41b3-8a76-a95376d97c66')
print(f"Status: {task.status}")
print(f"Result: {task.result}")
print(f"Error: {task.error}")
```

### Manual Task Execution

You can trigger tasks manually for testing:

```bash
# Manually process scheduled posts (APScheduler)
docker exec postflow_django python manage.py run_post_scheduled

# Manually refresh Instagram tokens (APScheduler)
docker exec postflow_django python manage.py refresh_instagram_tokens

# Manually sync Pixelfed posts (Django Tasks)
docker exec postflow_django python manage.py sync_pixelfed_posts --account-id 1

# Manually fetch engagement (Django Tasks)
docker exec postflow_django python manage.py fetch_pixelfed_engagement --account-id 1
```

### Restarting the Scheduler

```bash
# Restart entire Django container (cleanest approach)
docker-compose restart django

# Or rebuild if code changed
docker-compose up --build -d django
```

## Troubleshooting

### Background Processes Not Starting

**Symptom**: Health check fails, no process logs

**Solutions:**
```bash
# Check for scheduler lock file from crashed process
docker exec postflow_django ls -la /tmp/postflow_scheduler.lock
docker exec postflow_django rm /tmp/postflow_scheduler.lock

# Check entrypoint.sh logs
docker-compose logs django | grep -i "scheduler\|db_worker"

# Verify APScheduler is installed
docker exec postflow_django python -c "import apscheduler; print(apscheduler.__version__)"

# Verify django-tasks is installed
docker exec postflow_django python -c "import django_tasks; print('django-tasks installed')"

# Check if processes are running
docker exec postflow_django pgrep -f "run_scheduler"
docker exec postflow_django pgrep -f "db_worker"
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

### Background Tasks Not Processing

**Symptom**: Tasks remain in "pending" status, engagement not updating

**Debug steps:**
```bash
# Check if db_worker is running
docker exec postflow_django pgrep -f "db_worker"

# Check task queue
docker exec postflow_django python manage.py shell
>>> from django_tasks.models import TaskResult
>>> TaskResult.objects.filter(status='pending').count()

# View recent task failures
>>> failed_tasks = TaskResult.objects.filter(status='failed').order_by('-enqueued_at')[:5]
>>> for task in failed_tasks:
...     print(f"Task: {task.task_path}")
...     print(f"Error: {task.error}")

# Check worker logs for errors
docker-compose logs django | grep -i "db_worker\|task error"

# Restart db_worker
docker-compose restart django
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
