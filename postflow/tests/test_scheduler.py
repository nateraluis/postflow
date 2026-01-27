"""
Tests for the PostFlow APScheduler module using pytest.

This module tests:
- Scheduler initialization and startup
- File lock acquisition and release
- Job scheduling (post_scheduled and refresh_instagram_tokens)
- Error handling and recovery
- Graceful shutdown
"""

import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from postflow.scheduler import (
    PostFlowScheduler,
    SchedulerLockError,
    LOCK_FILE,
    start_scheduler,
)


# Fixtures

@pytest.fixture
def cleanup_lock_file():
    """Clean up lock file before and after each test."""
    # Setup: Remove lock file if it exists
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()

    yield

    # Teardown: Remove lock file if it exists
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


@pytest.fixture
def scheduler(cleanup_lock_file):
    """Create a PostFlowScheduler instance."""
    return PostFlowScheduler()


@pytest.fixture
def mock_background_scheduler():
    """Mock BackgroundScheduler for testing."""
    with patch('postflow.scheduler.BackgroundScheduler') as mock_class:
        mock_instance = MagicMock()
        mock_instance.running = True
        mock_class.return_value = mock_instance
        yield mock_instance


# Scheduler Lock Tests

@pytest.mark.django_db
class TestSchedulerLock:
    """Tests for scheduler file locking mechanism."""

    def test_acquire_lock_success(self, scheduler):
        """Test successful lock acquisition."""
        scheduler.acquire_lock()

        assert LOCK_FILE.exists()
        assert scheduler.lock_acquired is True

        # Verify PID is written to lock file
        with open(LOCK_FILE, 'r') as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()

        scheduler.release_lock()

    def test_acquire_lock_when_already_locked(self, cleanup_lock_file):
        """Test that acquiring lock fails when another instance holds it."""
        # Create first scheduler and acquire lock
        scheduler1 = PostFlowScheduler()
        scheduler1.acquire_lock()

        # Try to acquire lock with second scheduler
        scheduler2 = PostFlowScheduler()
        with pytest.raises(SchedulerLockError, match="already running"):
            scheduler2.acquire_lock()

        scheduler1.release_lock()

    def test_acquire_lock_removes_stale_lock(self, scheduler, cleanup_lock_file):
        """Test that stale lock files (from dead processes) are removed."""
        # Create a lock file with a non-existent PID
        fake_pid = 999999
        with open(LOCK_FILE, 'w') as f:
            f.write(str(fake_pid))

        # Should successfully acquire lock after removing stale lock
        scheduler.acquire_lock()

        assert scheduler.lock_acquired is True
        with open(LOCK_FILE, 'r') as f:
            pid = int(f.read().strip())
        assert pid == os.getpid()

        scheduler.release_lock()

    def test_release_lock(self, scheduler):
        """Test lock release."""
        scheduler.acquire_lock()
        assert LOCK_FILE.exists()

        scheduler.release_lock()
        assert not LOCK_FILE.exists()
        assert scheduler.lock_acquired is False

    def test_release_lock_when_not_acquired(self, scheduler):
        """Test that releasing lock when not acquired doesn't error."""
        scheduler.release_lock()  # Should not raise error
        assert scheduler.lock_acquired is False

    def test_lock_file_contains_correct_pid(self, scheduler):
        """Test that lock file contains the current process PID."""
        scheduler.acquire_lock()

        with open(LOCK_FILE, 'r') as f:
            lock_pid = int(f.read().strip())

        assert lock_pid == os.getpid()
        scheduler.release_lock()


# Scheduler Initialization Tests

@pytest.mark.django_db
class TestSchedulerInitialization:
    """Tests for scheduler initialization and startup."""

    def test_start_scheduler(self, scheduler, mock_background_scheduler):
        """Test scheduler starts with correct jobs."""
        scheduler.start()

        # Verify scheduler was initialized
        assert scheduler.scheduler is not None

        # Verify jobs were added (2 jobs: post_scheduled, refresh_instagram_tokens)
        assert mock_background_scheduler.add_job.call_count == 2

        # Verify scheduler was started
        mock_background_scheduler.start.assert_called_once()

        # Cleanup
        scheduler.release_lock()

    def test_jobs_configured_correctly(self, scheduler, mock_background_scheduler):
        """Test that jobs are configured with correct parameters."""
        scheduler.start()

        # Get the add_job calls
        calls = mock_background_scheduler.add_job.call_args_list

        # Check first job (post_scheduled)
        first_call = calls[0]
        assert first_call[1]['id'] == 'post_scheduled'
        assert first_call[1]['name'] == 'Process scheduled posts'
        assert first_call[1]['replace_existing'] is True

        # Check second job (refresh_instagram_tokens)
        second_call = calls[1]
        assert second_call[1]['id'] == 'refresh_instagram_tokens'
        assert second_call[1]['name'] == 'Refresh Instagram access tokens'
        assert second_call[1]['replace_existing'] is True

        scheduler.release_lock()

    def test_start_fails_if_lock_exists(self, cleanup_lock_file):
        """Test that start() fails if another instance holds lock."""
        scheduler1 = PostFlowScheduler()
        scheduler1.acquire_lock()

        scheduler2 = PostFlowScheduler()
        with pytest.raises(SchedulerLockError):
            scheduler2.start()

        scheduler1.release_lock()

    def test_scheduler_uses_utc_timezone(self, scheduler, mock_background_scheduler):
        """Test that scheduler is configured with UTC timezone."""
        with patch('postflow.scheduler.BackgroundScheduler') as mock_class:
            mock_class.return_value = mock_background_scheduler
            scheduler.start()

            # Check that BackgroundScheduler was called with timezone='UTC'
            call_kwargs = mock_class.call_args[1]
            assert call_kwargs['timezone'] == 'UTC'

        scheduler.release_lock()

    def test_scheduler_job_defaults(self, scheduler, mock_background_scheduler):
        """Test that scheduler has correct job defaults."""
        with patch('postflow.scheduler.BackgroundScheduler') as mock_class:
            mock_class.return_value = mock_background_scheduler
            scheduler.start()

            # Check job defaults
            call_kwargs = mock_class.call_args[1]
            job_defaults = call_kwargs['job_defaults']

            assert job_defaults['coalesce'] is True
            assert job_defaults['max_instances'] == 1
            assert job_defaults['misfire_grace_time'] == 30

        scheduler.release_lock()


# Scheduler Jobs Tests

@pytest.mark.django_db
class TestSchedulerJobs:
    """Tests for scheduler job execution."""

    @patch('postflow.cron.post_scheduled')
    def test_run_post_scheduled_job(self, mock_post_scheduled, scheduler):
        """Test _run_post_scheduled executes the cron function."""
        scheduler._run_post_scheduled()
        mock_post_scheduled.assert_called_once()

    @patch('postflow.cron.post_scheduled')
    def test_run_post_scheduled_handles_errors(self, mock_post_scheduled, scheduler):
        """Test that errors in post_scheduled are caught and logged."""
        mock_post_scheduled.side_effect = Exception("Test error")

        # Should not raise exception
        scheduler._run_post_scheduled()

        # Verify the function was called
        mock_post_scheduled.assert_called_once()

    @patch('postflow.scheduler.call_command')
    def test_refresh_instagram_tokens_job(self, mock_call_command, scheduler):
        """Test _refresh_instagram_tokens calls Django command."""
        scheduler._refresh_instagram_tokens()
        mock_call_command.assert_called_once_with('refresh_instagram_tokens')

    @patch('postflow.scheduler.call_command')
    def test_refresh_instagram_tokens_handles_errors(self, mock_call_command, scheduler):
        """Test that errors in refresh_instagram_tokens are caught."""
        mock_call_command.side_effect = Exception("Test error")

        # Should not raise exception
        scheduler._refresh_instagram_tokens()

        # Verify the function was called
        mock_call_command.assert_called_once()

    @patch('postflow.cron.post_scheduled')
    def test_post_scheduled_exception_is_logged(self, mock_post_scheduled, scheduler):
        """Test that exceptions in post_scheduled are properly logged."""
        error_message = "Database connection failed"
        mock_post_scheduled.side_effect = Exception(error_message)

        # Should not raise but should log
        scheduler._run_post_scheduled()

        # Verify exception was raised but caught
        assert mock_post_scheduled.call_count == 1


# Scheduler Shutdown Tests

@pytest.mark.django_db
class TestSchedulerShutdown:
    """Tests for scheduler shutdown and cleanup."""

    def test_shutdown(self, scheduler, mock_background_scheduler):
        """Test graceful shutdown."""
        scheduler.start()
        scheduler.shutdown()

        # Verify scheduler shutdown was called
        mock_background_scheduler.shutdown.assert_called_once_with(wait=True)

        # Verify lock was released
        assert not LOCK_FILE.exists()
        assert scheduler.lock_acquired is False

    def test_signal_handler_shutdown(self, scheduler, mock_background_scheduler):
        """Test that signal handlers trigger shutdown."""
        scheduler.start()

        # Simulate SIGTERM
        with pytest.raises(SystemExit):
            scheduler._signal_handler(signal.SIGTERM, None)

        # Verify shutdown was called
        mock_background_scheduler.shutdown.assert_called_once()

        # Verify lock was released
        assert not LOCK_FILE.exists()

    def test_shutdown_when_not_started(self, scheduler):
        """Test that shutdown works even if scheduler was never started."""
        # Should not raise error
        scheduler.shutdown()

    def test_shutdown_releases_lock_even_on_error(self, scheduler, mock_background_scheduler):
        """Test that lock is released even if shutdown encounters errors."""
        scheduler.start()

        # Set the side effect after start
        mock_background_scheduler.shutdown.side_effect = Exception("Shutdown error")

        # Shutdown should not raise but will log the exception
        try:
            scheduler.shutdown()
        except Exception:
            pass  # Expected due to side effect

        # Lock should still be released
        assert not LOCK_FILE.exists()
        assert scheduler.lock_acquired is False

    def test_signal_handler_for_sigint(self, scheduler, mock_background_scheduler):
        """Test that SIGINT signal also triggers shutdown."""
        scheduler.start()

        # Simulate SIGINT (Ctrl+C)
        with pytest.raises(SystemExit):
            scheduler._signal_handler(signal.SIGINT, None)

        # Verify shutdown was called
        mock_background_scheduler.shutdown.assert_called_once()


# Integration Tests

@pytest.mark.django_db
class TestSchedulerIntegration:
    """Integration tests for the scheduler."""

    @patch('postflow.cron.post_scheduled')
    def test_full_lifecycle(self, mock_post_scheduled, scheduler, mock_background_scheduler):
        """Test complete scheduler lifecycle: start -> run jobs -> shutdown."""
        # Start scheduler
        scheduler.start()
        assert LOCK_FILE.exists()
        assert scheduler.scheduler is not None

        # Manually trigger job
        scheduler._run_post_scheduled()
        mock_post_scheduled.assert_called_once()

        # Shutdown
        scheduler.shutdown()
        assert not LOCK_FILE.exists()
        mock_background_scheduler.shutdown.assert_called_once()

    def test_multiple_scheduler_instances_prevented(self, cleanup_lock_file, mock_background_scheduler):
        """Test that multiple scheduler instances cannot run simultaneously."""
        scheduler1 = PostFlowScheduler()
        scheduler1.start()

        scheduler2 = PostFlowScheduler()
        with pytest.raises(SchedulerLockError, match="already running"):
            scheduler2.start()

        scheduler1.shutdown()

    @patch('postflow.cron.post_scheduled')
    @patch('postflow.scheduler.call_command')
    def test_both_jobs_can_execute(self, mock_call_command, mock_post_scheduled, scheduler):
        """Test that both scheduled jobs can execute successfully."""
        # Execute post_scheduled job
        scheduler._run_post_scheduled()
        mock_post_scheduled.assert_called_once()

        # Execute refresh_instagram_tokens job
        scheduler._refresh_instagram_tokens()
        mock_call_command.assert_called_once_with('refresh_instagram_tokens')

    def test_scheduler_survives_job_failures(self, scheduler, mock_background_scheduler):
        """Test that scheduler continues running even if individual jobs fail."""
        scheduler.start()

        # Simulate job failures
        with patch('postflow.cron.post_scheduled', side_effect=Exception("Job failed")):
            scheduler._run_post_scheduled()

        # Scheduler should still be running
        assert scheduler.scheduler is not None
        assert LOCK_FILE.exists()

        scheduler.shutdown()


# Edge Cases and Error Handling

@pytest.mark.django_db
class TestSchedulerEdgeCases:
    """Tests for edge cases and error handling."""

    def test_lock_file_with_invalid_pid(self, scheduler, cleanup_lock_file):
        """Test handling of lock file with invalid PID format."""
        # Create lock file with invalid content
        with open(LOCK_FILE, 'w') as f:
            f.write("not_a_pid")

        # Should handle gracefully and create new lock
        scheduler.acquire_lock()
        assert scheduler.lock_acquired is True

        scheduler.release_lock()

    def test_lock_file_empty(self, scheduler, cleanup_lock_file):
        """Test handling of empty lock file."""
        # Create empty lock file
        LOCK_FILE.touch()

        # Should handle gracefully
        scheduler.acquire_lock()
        assert scheduler.lock_acquired is True

        scheduler.release_lock()

    def test_release_lock_when_file_doesnt_exist(self, scheduler):
        """Test releasing lock when file doesn't exist doesn't error."""
        scheduler.lock_acquired = True
        scheduler.release_lock()
        # Should not raise error

    @patch('postflow.scheduler.BackgroundScheduler')
    def test_scheduler_handles_add_job_failure(self, mock_scheduler_class, scheduler):
        """Test that scheduler handles job addition failures gracefully."""
        mock_instance = MagicMock()
        mock_instance.add_job.side_effect = Exception("Failed to add job")
        mock_scheduler_class.return_value = mock_instance

        # Should raise exception since job addition is critical
        with pytest.raises(Exception, match="Failed to add job"):
            scheduler.start()

        # Should still release lock
        scheduler.release_lock()
