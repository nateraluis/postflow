"""
Pytest configuration for PostFlow tests.

This file configures pytest-django and provides global fixtures.
"""

import os
import sys
from pathlib import Path

import django
from django.conf import settings
import pytest

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def pytest_configure(config):
    """
    Configure Django settings for pytest.

    This runs before any tests are collected.
    """
    # Set the Django settings module environment variable
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

    # Setup Django
    django.setup()


@pytest.fixture(scope='session', autouse=True)
def enable_debug_mode(django_db_setup, django_db_blocker):
    """
    Enable DEBUG mode for all tests to bypass subscription middleware.

    This fixture runs automatically for all tests and ensures that
    the subscription middleware is bypassed during testing.
    """
    with django_db_blocker.unblock():
        from django.conf import settings
        settings.DEBUG = True
