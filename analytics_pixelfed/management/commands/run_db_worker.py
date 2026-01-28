"""
Django management command to start the Django tasks database worker.

Usage:
    python manage.py run_db_worker

This command starts the django-tasks database worker that processes
background tasks from the task queue. It runs as a long-lived process
and should be started in the Docker entrypoint script.
"""

import logging
from django.core.management import call_command
from django.core.management.base import BaseCommand

logger = logging.getLogger('postflow')


class Command(BaseCommand):
    help = 'Starts the Django tasks database worker to process background tasks'

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            '--reload',
            action='store_true',
            help='Auto-reload worker when code changes (development only)',
        )

    def handle(self, *args, **options):
        """
        Start the database worker and block until interrupted.

        The worker will run indefinitely, processing:
        - Pixelfed engagement fetch tasks
        - Pixelfed post sync tasks
        - Other background analytics tasks
        """
        self.stdout.write(
            self.style.SUCCESS('Starting Django tasks database worker...')
        )

        try:
            # Call the built-in db_worker management command
            logger.info("Django tasks database worker starting...")

            # Pass through any options
            worker_options = {}
            if options.get('reload'):
                worker_options['reload'] = True
                logger.info("Auto-reload enabled for worker")

            call_command('db_worker', **worker_options)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('\nDatabase worker stopped by user')
            )
            logger.info("Database worker stopped by user")
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Database worker error: {e}')
            )
            logger.exception(f"Database worker error: {e}")
            raise
