"""
Django management command to start the PostFlow scheduler.

Usage:
    python manage.py run_scheduler

This command starts the APScheduler-based task scheduler that replaces
system cron. It runs as a long-lived process and should be started in
the Docker entrypoint script.
"""

from django.core.management.base import BaseCommand
from postflow.scheduler import start_scheduler, SchedulerLockError


class Command(BaseCommand):
    help = 'Starts the PostFlow APScheduler to process scheduled tasks'

    def handle(self, *args, **options):
        """
        Start the scheduler and block until interrupted.

        The scheduler will run indefinitely, processing:
        - Scheduled posts every minute
        - Instagram token refresh every 6 hours
        """
        self.stdout.write(
            self.style.SUCCESS('Starting PostFlow scheduler...')
        )

        try:
            start_scheduler()
        except SchedulerLockError as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to start scheduler: {e}')
            )
            self.stdout.write(
                self.style.WARNING(
                    'Another scheduler instance may already be running. '
                    'Check for existing processes or stale lock files.'
                )
            )
            raise SystemExit(1)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('\nScheduler stopped by user')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Scheduler error: {e}')
            )
            raise
