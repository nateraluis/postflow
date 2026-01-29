"""
App configuration for Pixelfed Analytics.

Schedules hourly background tasks to fetch engagement metrics.
"""
from django.apps import AppConfig


class AnalyticsPixelfedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics_pixelfed'
    verbose_name = 'Pixelfed Analytics'

    def ready(self):
        """
        Initialize app and schedule background tasks.

        This runs when Django starts. It schedules hourly engagement fetching
        using django-tasks.
        """
        # Import here to avoid AppRegistryNotReady error
        # Note: Auto-scheduling disabled for now - tasks can be triggered manually
        # or via cron/APScheduler. django-tasks will be used for execution only.
        import logging

        # Import signals to register them
        from . import signals

        logger = logging.getLogger('postflow')
        logger.info("Pixelfed Analytics app ready")
