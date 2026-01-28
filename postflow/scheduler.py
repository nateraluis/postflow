"""
APScheduler-based task scheduler for PostFlow.

This module provides a reliable Python-based scheduler that replaces system cron.
It ensures scheduled posts are processed every minute and Instagram tokens are
refreshed every 6 hours.
"""

import logging
import os
import signal
import sys
import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from django.core.management import call_command

logger = logging.getLogger("postflow")

# File lock to prevent multiple scheduler instances
LOCK_FILE = Path("/tmp/postflow_scheduler.lock")


class SchedulerLockError(Exception):
    """Raised when scheduler lock cannot be acquired."""
    pass


class PostFlowScheduler:
    """
    Manages scheduled tasks for PostFlow using APScheduler.

    Implements file-based locking to ensure only one scheduler instance runs.
    Handles graceful shutdown on SIGTERM and SIGINT signals.
    """

    def __init__(self):
        self.scheduler = None
        self.lock_acquired = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Set up handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down scheduler...")
        self.shutdown()
        sys.exit(0)

    def acquire_lock(self):
        """
        Acquire file lock to prevent multiple scheduler instances.

        Raises:
            SchedulerLockError: If lock file already exists
        """
        if LOCK_FILE.exists():
            # Check if the process holding the lock is still alive
            try:
                with open(LOCK_FILE, 'r') as f:
                    old_pid = int(f.read().strip())

                # Try to check if process exists (Unix only)
                try:
                    os.kill(old_pid, 0)
                    # Process exists, lock is valid
                    raise SchedulerLockError(
                        f"Scheduler already running with PID {old_pid}. "
                        f"Lock file: {LOCK_FILE}"
                    )
                except OSError:
                    # Process doesn't exist, remove stale lock
                    logger.warning(f"Removing stale lock file for PID {old_pid}")
                    LOCK_FILE.unlink()
            except (ValueError, FileNotFoundError):
                # Invalid lock file, remove it
                logger.warning("Removing invalid lock file")
                LOCK_FILE.unlink()

        # Create lock file with current PID
        try:
            with open(LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
            self.lock_acquired = True
            logger.info(f"Scheduler lock acquired (PID: {os.getpid()})")
        except Exception as e:
            raise SchedulerLockError(f"Failed to create lock file: {e}")

    def release_lock(self):
        """Release the scheduler lock file."""
        if self.lock_acquired and LOCK_FILE.exists():
            try:
                LOCK_FILE.unlink()
                self.lock_acquired = False
                logger.info("Scheduler lock released")
            except Exception as e:
                logger.error(f"Failed to release lock: {e}")

    def start(self):
        """
        Start the APScheduler with all configured jobs.

        Jobs:
        - post_scheduled: Runs every minute to process pending posts
        - refresh_instagram_tokens: Runs every 6 hours to refresh Instagram tokens
        - sync_pixelfed_posts: Runs every hour to sync posts from Pixelfed accounts
        - fetch_pixelfed_engagement: Runs every hour to fetch engagement metrics
        """
        # Acquire lock first
        self.acquire_lock()

        # Initialize scheduler
        self.scheduler = BackgroundScheduler(
            timezone='UTC',
            job_defaults={
                'coalesce': True,  # Combine multiple missed executions into one
                'max_instances': 1,  # Only one instance of each job at a time
                'misfire_grace_time': 30,  # Allow 30 seconds grace for missed jobs
            }
        )

        # Add job: Process scheduled posts every minute
        self.scheduler.add_job(
            func=self._run_post_scheduled,
            trigger=IntervalTrigger(minutes=1),
            id='post_scheduled',
            name='Process scheduled posts',
            replace_existing=True,
        )
        logger.info("Added job: post_scheduled (every 1 minute)")

        # Add job: Refresh Instagram tokens every 6 hours
        # Runs at 00:00, 06:00, 12:00, 18:00 UTC
        self.scheduler.add_job(
            func=self._refresh_instagram_tokens,
            trigger=CronTrigger(hour='*/6', minute=0),
            id='refresh_instagram_tokens',
            name='Refresh Instagram access tokens',
            replace_existing=True,
        )
        logger.info("Added job: refresh_instagram_tokens (every 6 hours at :00)")

        # Add job: Sync Pixelfed posts every hour
        # Runs at :15 past every hour (offset to avoid collision with token refresh)
        self.scheduler.add_job(
            func=self._sync_pixelfed_posts,
            trigger=CronTrigger(hour='*', minute=15),
            id='sync_pixelfed_posts',
            name='Sync Pixelfed posts',
            replace_existing=True,
        )
        logger.info("Added job: sync_pixelfed_posts (every hour at :15)")

        # Add job: Fetch Pixelfed engagement every hour
        # Runs at :45 past every hour (offset from post sync)
        self.scheduler.add_job(
            func=self._fetch_pixelfed_engagement,
            trigger=CronTrigger(hour='*', minute=45),
            id='fetch_pixelfed_engagement',
            name='Fetch Pixelfed engagement',
            replace_existing=True,
        )
        logger.info("Added job: fetch_pixelfed_engagement (every hour at :45)")

        # Start the scheduler
        self.scheduler.start()
        logger.info("PostFlow scheduler started successfully")

        # Print scheduled jobs for debugging
        jobs = self.scheduler.get_jobs()
        logger.info(f"Scheduled {len(jobs)} job(s):")
        for job in jobs:
            logger.info(f"  - {job.name} (ID: {job.id}, Next run: {job.next_run_time})")

    def _run_post_scheduled(self):
        """
        Execute the post_scheduled task.
        Wraps the cron.post_scheduled() function with error handling.
        """
        try:
            from postflow.cron import post_scheduled
            logger.debug("Running post_scheduled job...")
            post_scheduled()
        except Exception as e:
            logger.exception(f"Error in post_scheduled job: {e}")

    def _refresh_instagram_tokens(self):
        """
        Execute the refresh_instagram_tokens task.
        Calls the Django management command with error handling.
        """
        try:
            logger.debug("Running refresh_instagram_tokens job...")
            call_command('refresh_instagram_tokens')
        except Exception as e:
            logger.exception(f"Error in refresh_instagram_tokens job: {e}")

    def _sync_pixelfed_posts(self):
        """
        Sync posts from all Pixelfed accounts.
        Enqueues a Django task to run in the background.
        """
        try:
            from analytics_pixelfed.tasks import sync_all_pixelfed_posts
            logger.debug("Enqueuing sync_all_pixelfed_posts task...")
            task = sync_all_pixelfed_posts.enqueue()
            logger.info(f"Enqueued sync_all_pixelfed_posts task: {task.id}")
        except Exception as e:
            logger.exception(f"Error enqueueing sync_all_pixelfed_posts: {e}")

    def _fetch_pixelfed_engagement(self):
        """
        Fetch engagement metrics for all Pixelfed accounts.
        Enqueues a Django task to run in the background.
        """
        try:
            from analytics_pixelfed.tasks import fetch_all_pixelfed_engagement
            logger.debug("Enqueuing fetch_all_pixelfed_engagement task...")
            task = fetch_all_pixelfed_engagement.enqueue()
            logger.info(f"Enqueued fetch_all_pixelfed_engagement task: {task.id}")
        except Exception as e:
            logger.exception(f"Error enqueueing fetch_all_pixelfed_engagement: {e}")

    def shutdown(self):
        """Gracefully shut down the scheduler and release lock."""
        try:
            if self.scheduler and self.scheduler.running:
                logger.info("Shutting down scheduler...")
                self.scheduler.shutdown(wait=True)
                logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
        finally:
            # Always release the lock, even if shutdown fails
            self.release_lock()

    def run_forever(self):
        """
        Start scheduler and block forever.
        Used by the management command to keep the process alive.
        """
        self.start()

        try:
            # Keep the main thread alive
            logger.info("Scheduler running. Press Ctrl+C to exit.")
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Received shutdown signal")
        finally:
            self.shutdown()


def start_scheduler():
    """
    Helper function to start the scheduler.

    This is the main entry point used by the management command.

    Raises:
        SchedulerLockError: If another scheduler instance is already running
    """
    scheduler = PostFlowScheduler()
    scheduler.run_forever()
