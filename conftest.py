"""
Pytest configuration for PostFlow tests.

This file configures pytest-django and provides global fixtures.
"""

import os
import sys
from pathlib import Path

import django
from django.conf import settings

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
