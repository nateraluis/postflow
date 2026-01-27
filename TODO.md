# PostFlow Analytics Refactor - Platform-Independent Architecture

## Overview
Build a scalable, platform-independent analytics system starting with Pixelfed. The system fetches ALL posts with media from connected social accounts (not just posts created via PostFlow), tracks granular engagement (likes, comments, shares with timestamps), and provides cross-platform insights. Uses Django 6.0.1 with django-tasks for automated hourly fetching.

## Key Architecture Decisions

1. **Separate Django Apps Per Platform**: `analytics_pixelfed/`, `analytics_instagram/` (future), `analytics_mastodon/` (future), `analytics/` (unified core)
2. **Independent from PostFlow Posting**: Fetches ALL posts from connected accounts, not just ScheduledPost records
3. **Media-Only Posts**: Only fetch and track posts that contain photos/videos (skip text-only posts)
4. **Granular Engagement**: Track individual likes, comments, shares with timestamps and usernames
5. **Cross-Platform Dashboard**: Unified analytics view comparing performance across all platforms
6. **Hourly Automation**: Background tasks fetch analytics every hour using django-tasks
7. **Performance Target**: Fast loading (<3s), support 100s of users, 30-50 posts/month each

---

## Phase 1: Remove Current Analytics Implementation

### US-1.1: Remove Analytics Scheduler Job
**As a** developer
**I want to** remove the analytics scheduler job from APScheduler
**So that** we don't have conflicting analytics fetching systems

**Acceptance Criteria:**
- Remove `fetch_analytics` job from `postflow/scheduler.py` (line with `add_job` and `id='fetch_analytics'`)
- Remove `_fetch_analytics` method from PostFlowScheduler class
- Verify scheduler still runs: `docker-compose logs django | grep scheduler`
- Test remaining jobs work: check logs for `post_scheduled` and `refresh_instagram_tokens` execution
- No errors in scheduler startup

**Files to modify:**
- `postflow/scheduler.py`

**Technical Details:**
- Keep other scheduler jobs intact (post_scheduled, refresh_instagram_tokens)
- Ensure file lock mechanism still works
- Verify CronTrigger imports are cleaned up if unused

---

### US-1.2: Remove Analytics Management Command
**As a** developer
**I want to** remove the old fetch_analytics management command
**So that** we don't accidentally use the old implementation

**Acceptance Criteria:**
- Delete `analytics/management/commands/fetch_analytics.py`
- If `analytics/management/commands/` is empty, delete the entire directory structure
- Run `uv run manage.py` and verify `fetch_analytics` is not listed
- Check for imports of this command in other files: `grep -r "call_command('fetch_analytics'" .`

**Files to delete:**
- `analytics/management/commands/fetch_analytics.py`
- `analytics/management/commands/__init__.py` (if directory becomes empty)
- `analytics/management/` (if empty)

---

### US-1.3: Remove Analytics Utils and Services
**As a** developer
**I want to** remove old analytics fetching utilities
**So that** we have a clean slate for new implementation

**Acceptance Criteria:**
- Delete `analytics/utils.py` file
- Search codebase for imports: `grep -r "from analytics.utils" .` and `grep -r "import analytics.utils" .`
- Remove any found imports
- Verify no broken imports: `uv run python manage.py check`

**Files to delete:**
- `analytics/utils.py`

**Files to check for imports:**
- `analytics/views.py`
- `postflow/scheduler.py`
- Any other app files

---

### US-1.4: Remove Analytics Views and Templates
**As a** developer
**I want to** remove old analytics views and templates
**So that** we can rebuild with new architecture

**Acceptance Criteria:**
- Delete all view functions in `analytics/views.py` (keep file with empty content or single comment)
- Delete entire `analytics/templates/` directory
- Comment out all urlpatterns in `analytics/urls.py`: wrap in `"""` comment block
- Access `http://localhost:8000/analytics/` and verify 404 or empty response
- Run `uv run manage.py check` to ensure no broken references

**Files to modify:**
- `analytics/views.py` - replace content with `# Views will be rebuilt in new architecture`
- `analytics/urls.py` - comment out urlpatterns, keep app_name

**Files to delete:**
- `analytics/templates/analytics/dashboard.html`
- `analytics/templates/analytics/post_detail.html`
- `analytics/templates/analytics/` (entire directory)

---

### US-1.5: Remove Analytics Models
**As a** developer
**I want to** remove the old PostAnalytics model
**So that** we can create new models for platform-independent architecture

**Acceptance Criteria:**
- Delete `PostAnalytics` class from `analytics/models.py`
- Create migration: `uv run manage.py makemigrations analytics --name remove_old_analytics`
- Migration should contain `migrations.DeleteModel(name='PostAnalytics')`
- Run migration in development: `uv run manage.py migrate analytics`
- Verify table dropped: `psql` and `\dt analytics_*` shows no postanalytics table
- Remove PostAnalyticsAdmin from `analytics/admin.py`
- Run `uv run manage.py check` - no errors

**Files to modify:**
- `analytics/models.py` - delete PostAnalytics class, keep file with base imports
- `analytics/admin.py` - remove admin.register and PostAnalyticsAdmin class
- Create new migration file

**Migration validation:**
```python
# Expected migration content
operations = [
    migrations.DeleteModel(name='PostAnalytics'),
]
```

---

### US-1.6: Remove Analytics Tests
**As a** developer
**I want to** remove old analytics tests
**So that** we can write new tests for new implementation

**Acceptance Criteria:**
- Delete `analytics/tests/test_models.py`
- Delete `analytics/tests/test_views.py`
- Delete `analytics/tests/test_utils.py`
- Keep `analytics/tests/__init__.py` (empty file)
- Run `uv run pytest analytics/` and verify "no tests ran" or similar message
- Run full test suite: `uv run pytest` and verify no collection errors

**Files to delete:**
- `analytics/tests/test_models.py`
- `analytics/tests/test_views.py`
- `analytics/tests/test_utils.py`

**Files to keep:**
- `analytics/tests/__init__.py`

---

## Phase 2: Upgrade to Django 6.0.1 and Install django-tasks

### US-2.1: Upgrade Django to 6.0.1
**As a** developer
**I want to** upgrade to Django 6.0.1
**So that** I can use modern Django features and django-tasks compatibility

**Acceptance Criteria:**
- Update `pyproject.toml`: change `django>=5.2.7` to `django>=6.0.1`
- Run `uv sync` successfully (no dependency conflicts)
- Verify Django version: `uv run python -c "import django; print(django.VERSION)"` shows `(6, 0, 1, 'final', 0)` or higher
- Run `uv run manage.py check` - no errors
- Run existing test suite: `uv run pytest` - all tests pass
- Check for deprecation warnings: `uv run manage.py check --deploy`
- Review Django 6.0 release notes for breaking changes: https://docs.djangoproject.com/en/6.0/releases/6.0/
- Test local development server: `uv run manage.py runserver` and access homepage

**Files to modify:**
- `pyproject.toml` (line 10)

**Rollback plan:**
- If issues occur, revert to `django>=5.2.7` and run `uv sync`

**Known Django 6.0 changes to review:**
- New background tasks API (TASKS setting)
- Database backend updates
- Async view support improvements
- Security enhancements

---

### US-2.2: Install and Configure django-tasks
**As a** developer
**I want to** install django-tasks with database backend
**So that** I can schedule hourly analytics fetching

**Acceptance Criteria:**
- Add `django-tasks[database]>=2.8.0` to `pyproject.toml` dependencies array
- Run `uv sync` successfully
- Add `django_tasks` to `INSTALLED_APPS` in `core/settings.py` (after analytics)
- Run `uv run manage.py migrate` - creates django_tasks tables
- Verify tables exist: `psql` → `\dt django_tasks_*`
- Check available management commands: `uv run manage.py` should show tasks-related commands

**Files to modify:**
- `pyproject.toml` - add to dependencies array
- `core/settings.py` - add to INSTALLED_APPS

**Expected tables created:**
- `django_tasks_task`
- `django_tasks_taskresult`
- Database backend queue tables

**Documentation reference:**
- https://github.com/RealOrangeOne/django-tasks

---

### US-2.3: Configure django-tasks Database Backend
**As a** developer
**I want to** configure django-tasks to use database backend
**So that** tasks persist across server restarts and can be monitored

**Acceptance Criteria:**
- Add `TASKS` configuration to `core/settings.py` (after DATABASES section)
- Use database backend for both development and production
- Configuration specifies default queue and backend class
- Verify config: `uv run python manage.py shell` → `from django.conf import settings; print(settings.TASKS)`
- No errors when importing django_tasks: `python -c "import django_tasks; print('OK')"`

**Files to modify:**
- `core/settings.py`

**Configuration to add:**
```python
# Django Tasks Configuration
TASKS = {
    "default": {
        "BACKEND": "django_tasks.backends.database.DatabaseBackend",
        "QUEUES": ["default"],
    }
}
```

**Validation:**
- Settings properly loaded
- No import errors
- Compatible with PostgreSQL backend

---

## Phase 3: Create analytics_pixelfed App

### US-3.1: Create analytics_pixelfed Django App
**As a** developer
**I want to** create a new Django app for Pixelfed analytics
**So that** Pixelfed analytics are isolated and maintainable

**Acceptance Criteria:**
- Run `uv run manage.py startapp analytics_pixelfed`
- Add `analytics_pixelfed` to `INSTALLED_APPS` in `core/settings.py` (after `analytics`)
- Create directory structure:
  - `analytics_pixelfed/management/commands/`
  - `analytics_pixelfed/tests/`
  - `analytics_pixelfed/templates/analytics_pixelfed/`
- Set app config name in `analytics_pixelfed/apps.py`
- Verify app recognized: `uv run manage.py check`

**Files to create:**
- `analytics_pixelfed/__init__.py`
- `analytics_pixelfed/apps.py`
- `analytics_pixelfed/models.py`
- `analytics_pixelfed/admin.py`
- `analytics_pixelfed/views.py`
- `analytics_pixelfed/urls.py`
- `analytics_pixelfed/tests/__init__.py`
- `analytics_pixelfed/management/__init__.py`
- `analytics_pixelfed/management/commands/__init__.py`

**Files to modify:**
- `core/settings.py` - add to INSTALLED_APPS

**App config:**
```python
# analytics_pixelfed/apps.py
class AnalyticsPixelfedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics_pixelfed'
    verbose_name = 'Pixelfed Analytics'
```

---

### US-3.2: Create PixelfedPost Model
**As a** developer
**I want to** create a PixelfedPost model to store post metadata
**So that** we can track Pixelfed posts independently of ScheduledPost

**Acceptance Criteria:**
- Create `PixelfedPost` model in `analytics_pixelfed/models.py` with fields:
  - `scheduled_post` (ForeignKey to ScheduledPost, null=True, blank=True, on_delete=SET_NULL, related_name='pixelfed_analytics')
  - `pixelfed_post_id` (CharField, max_length=100, unique=True, db_index=True)
  - `account` (ForeignKey to pixelfed.MastodonAccount, on_delete=CASCADE, related_name='analytics_posts')
  - `instance_url` (URLField, max_length=255)
  - `username` (CharField, max_length=100)
  - `caption` (TextField, blank=True)
  - `media_url` (URLField, max_length=500) - primary image/video URL
  - `media_type` (CharField, max_length=20, choices=[('image', 'Image'), ('video', 'Video'), ('carousel', 'Carousel')])
  - `post_url` (URLField, max_length=500) - full URL to post
  - `posted_at` (DateTimeField, db_index=True)
  - `last_fetched_at` (DateTimeField, auto_now=True, db_index=True)
  - `created_at` (DateTimeField, auto_now_add=True)
- Add Meta class: unique_together on `(instance_url, pixelfed_post_id)`, indexes, ordering
- Add `__str__` method: return f"@{self.username} - {self.pixelfed_post_id}"
- Add property `has_media` → return True (all posts in this model have media)
- Add property `platform` → return 'pixelfed'
- Create migration: `uv run manage.py makemigrations analytics_pixelfed`
- Run migration: `uv run manage.py migrate analytics_pixelfed`

**Files to modify:**
- `analytics_pixelfed/models.py`

**Model code structure:**
```python
from django.db import models
from django.conf import settings
from postflow.models import ScheduledPost
from pixelfed.models import MastodonAccount

class PixelfedPost(models.Model):
    # Fields as specified above

    class Meta:
        db_table = 'analytics_pixelfed_post'
        unique_together = [('instance_url', 'pixelfed_post_id')]
        indexes = [
            models.Index(fields=['posted_at']),
            models.Index(fields=['last_fetched_at']),
            models.Index(fields=['account', 'posted_at']),
        ]
        ordering = ['-posted_at']
        verbose_name = 'Pixelfed Post'
        verbose_name_plural = 'Pixelfed Posts'

    def __str__(self):
        return f"@{self.username} - {self.pixelfed_post_id}"

    @property
    def platform(self):
        return 'pixelfed'
```

---

### US-3.3: Create PixelfedLike Model
**As a** developer
**I want to** create a PixelfedLike model to track individual likes
**So that** we can analyze who likes posts and when

**Acceptance Criteria:**
- Create `PixelfedLike` model with fields:
  - `post` (ForeignKey to PixelfedPost, on_delete=CASCADE, related_name='likes')
  - `account_id` (CharField, max_length=100) - Pixelfed account ID
  - `username` (CharField, max_length=100)
  - `display_name` (CharField, max_length=200, blank=True) - user's display name
  - `liked_at` (DateTimeField, db_index=True)
  - `created_at` (DateTimeField, auto_now_add=True)
- Add Meta: unique_together on `(post, account_id)`, indexes, ordering by -liked_at
- Add `__str__` method: return f"{self.username} liked {self.post.pixelfed_post_id}"
- Create migration

**Files to modify:**
- `analytics_pixelfed/models.py`

**Model structure:**
```python
class PixelfedLike(models.Model):
    post = models.ForeignKey(PixelfedPost, on_delete=models.CASCADE, related_name='likes')
    account_id = models.CharField(max_length=100)
    username = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200, blank=True)
    liked_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics_pixelfed_like'
        unique_together = [('post', 'account_id')]
        indexes = [
            models.Index(fields=['liked_at']),
            models.Index(fields=['username']),
        ]
        ordering = ['-liked_at']
        verbose_name = 'Pixelfed Like'
        verbose_name_plural = 'Pixelfed Likes'
```

---

### US-3.4: Create PixelfedComment Model
**As a** developer
**I want to** create a PixelfedComment model to track comments with threading
**So that** we can display comment conversations

**Acceptance Criteria:**
- Create `PixelfedComment` model with fields:
  - `post` (ForeignKey to PixelfedPost, CASCADE, related_name='comments')
  - `comment_id` (CharField, max_length=100, unique=True, db_index=True)
  - `account_id` (CharField, max_length=100)
  - `username` (CharField, max_length=100)
  - `display_name` (CharField, max_length=200, blank=True)
  - `content` (TextField) - comment text
  - `in_reply_to_id` (CharField, max_length=100, null=True, blank=True) - for threading
  - `commented_at` (DateTimeField, db_index=True)
  - `created_at` (DateTimeField, auto_now_add=True)
- Add Meta: unique constraint on comment_id, indexes, ordering by commented_at (oldest first)
- Add `__str__` method
- Add property `is_reply` → return bool(self.in_reply_to_id)
- Create migration

**Files to modify:**
- `analytics_pixelfed/models.py`

---

### US-3.5: Create PixelfedShare Model
**As a** developer
**I want to** create a PixelfedShare model to track shares/boosts
**So that** we can measure content virality

**Acceptance Criteria:**
- Create `PixelfedShare` model with fields:
  - `post` (ForeignKey to PixelfedPost, CASCADE, related_name='shares')
  - `account_id` (CharField, max_length=100)
  - `username` (CharField, max_length=100)
  - `display_name` (CharField, max_length=200, blank=True)
  - `shared_at` (DateTimeField, db_index=True)
  - `created_at` (DateTimeField, auto_now_add=True)
- Add Meta: unique_together on (post, account_id), indexes, ordering
- Add `__str__` method
- Create migration

**Files to modify:**
- `analytics_pixelfed/models.py`

---

### US-3.6: Create PixelfedEngagementSummary Model
**As a** developer
**I want to** create a summary model for cached counts
**So that** dashboard queries are fast

**Acceptance Criteria:**
- Create `PixelfedEngagementSummary` model with fields:
  - `post` (OneToOneField to PixelfedPost, CASCADE, related_name='engagement_summary')
  - `total_likes` (IntegerField, default=0, db_index=True)
  - `total_comments` (IntegerField, default=0)
  - `total_shares` (IntegerField, default=0)
  - `total_engagement` (IntegerField, default=0, db_index=True) - computed sum
  - `engagement_rate` (FloatField, null=True, blank=True) - future: likes+comments+shares / impressions
  - `last_updated` (DateTimeField, auto_now=True)
- Override save() to auto-calculate total_engagement
- Add method `update_from_post()` - recalculates counts from related likes/comments/shares
- Add `__str__` method
- Create migration

**Files to modify:**
- `analytics_pixelfed/models.py`

**update_from_post() logic:**
```python
def update_from_post(self):
    from django.db.models import Count
    self.total_likes = self.post.likes.count()
    self.total_comments = self.post.comments.count()
    self.total_shares = self.post.shares.count()
    self.save()  # save() will calculate total_engagement
```

---

### US-3.7: Add Helper Methods to PixelfedPost
**As a** developer
**I want to** add convenience methods to PixelfedPost
**So that** views can easily access engagement data

**Acceptance Criteria:**
- Add method `refresh_engagement_summary()` that:
  - Gets or creates PixelfedEngagementSummary
  - Calls `update_from_post()`
  - Returns the summary object
- Add cached_property `likes_count` → self.likes.count()
- Add cached_property `comments_count` → self.comments.count()
- Add cached_property `shares_count` → self.shares.count()
- Add method `get_recent_engagement(hours=24)` → returns dict with counts from last N hours
- Add method `get_top_likers(limit=10)` → returns queryset of most frequent likers
- Write docstrings for all methods

**Files to modify:**
- `analytics_pixelfed/models.py`

**Method signatures:**
```python
def refresh_engagement_summary(self):
    """Updates engagement summary from current like/comment/share counts"""

@cached_property
def likes_count(self):
    """Returns total number of likes"""

def get_recent_engagement(self, hours=24):
    """Returns engagement counts from last N hours"""

def get_top_likers(self, limit=10):
    """Returns users who liked most posts from this account"""
```

---

## Phase 4: Implement Pixelfed API Client

### US-4.1: Create Pixelfed API Client Class
**As a** developer
**I want to** create a robust Pixelfed API client
**So that** I can fetch post data and engagement reliably

**Acceptance Criteria:**
- Create `analytics_pixelfed/pixelfed_client.py`
- Implement `PixelfedAPIClient` class with:
  - Constructor: `__init__(instance_url, access_token)`
  - Validates and normalizes instance_url (remove trailing slash)
  - Stores base API URL
- Add private method `_make_request(endpoint, method='GET', params=None)`:
  - Makes HTTP request with auth header
  - Handles timeouts (30 seconds)
  - Returns response.json() or raises PixelfedAPIError
- Add custom exception `PixelfedAPIError(Exception)`
- Add logging for all API calls
- Add retry decorator with exponential backoff (max 3 retries, start at 1s)

**Files to create:**
- `analytics_pixelfed/pixelfed_client.py`

**Class structure:**
```python
import requests
import logging
from time import sleep
from functools import wraps

logger = logging.getLogger('postflow')

class PixelfedAPIError(Exception):
    """Raised when Pixelfed API returns an error"""
    pass

def retry_on_failure(max_retries=3, initial_delay=1):
    """Decorator for exponential backoff retry logic"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Implementation
            pass
        return wrapper
    return decorator

class PixelfedAPIClient:
    def __init__(self, instance_url, access_token):
        self.instance_url = instance_url.rstrip('/')
        self.access_token = access_token
        self.base_url = f"{self.instance_url}/api"

    @retry_on_failure(max_retries=3)
    def _make_request(self, endpoint, method='GET', params=None):
        # Implementation
        pass
```

**Rate limiting:**
- Sleep 1 second between requests (conservative)
- Log all requests with timestamp

---

### US-4.2: Implement Fetch User Posts Method
**As a** developer
**I want to** fetch all posts with media from a Pixelfed account
**So that** I can populate the analytics database

**Acceptance Criteria:**
- Add method `get_account_posts(account_id, max_id=None, limit=40)` to PixelfedAPIClient
- Uses endpoint: `/api/v1/accounts/{account_id}/statuses`
- Parameters: `max_id` (pagination), `limit` (per page), `only_media=true` (filter media posts)
- Returns list of post dicts
- Handles pagination via `max_id` from Link header
- Filters posts: only include posts with `media_attachments` array
- Logs number of posts fetched
- Raises PixelfedAPIError on HTTP errors

**Files to modify:**
- `analytics_pixelfed/pixelfed_client.py`

**Method signature:**
```python
def get_account_posts(self, account_id, max_id=None, limit=40):
    """
    Fetch posts from account that contain media.

    Args:
        account_id: Pixelfed account ID
        max_id: For pagination, fetch posts older than this ID
        limit: Number of posts per request (max 40)

    Returns:
        List of post dicts with media
    """
    params = {
        'limit': limit,
        'only_media': 'true',
    }
    if max_id:
        params['max_id'] = max_id

    endpoint = f"/v1/accounts/{account_id}/statuses"
    # Implementation
```

**API response parsing:**
- Check `media_attachments` is not empty
- Extract: id, content, created_at, url, media_attachments[0].url, media_attachments[0].type
- Handle missing fields gracefully

---

### US-4.3: Implement Fetch Post Likes Method
**As a** developer
**I want to** fetch all accounts who liked a post
**So that** I can track individual likes with timestamps

**Acceptance Criteria:**
- Add method `get_post_favourited_by(post_id, max_id=None, limit=80)` to PixelfedAPIClient
- Uses endpoint: `/api/v1/statuses/{post_id}/favourited_by`
- Handles pagination (Link header)
- Returns list of account dicts with: id, username, display_name, created_at (of the like)
- Note: Pixelfed API doesn't return like timestamps, use fetch time as approximation
- Fetches ALL pages until no more results
- Logs total likes fetched per post
- Rate limit: 1 second between pagination requests

**Files to modify:**
- `analytics_pixelfed/pixelfed_client.py`

**Method signature:**
```python
def get_post_favourited_by(self, post_id, max_id=None, limit=80):
    """
    Fetch all accounts who favorited/liked a post.
    Handles pagination automatically.

    Args:
        post_id: Pixelfed post ID
        max_id: For pagination
        limit: Results per page

    Returns:
        List of account dicts: [{id, username, display_name}, ...]
    """
```

**Pagination handling:**
```python
all_likes = []
while True:
    response = self._make_request(endpoint, params={'max_id': max_id, 'limit': limit})
    all_likes.extend(response)

    # Check for Link header with next page
    if not response or len(response) < limit:
        break

    max_id = response[-1]['id']
    sleep(1)  # Rate limiting

return all_likes
```

---

### US-4.4: Implement Fetch Post Comments Method
**As a** developer
**I want to** fetch all comments/replies on a post
**So that** I can display comment threads

**Acceptance Criteria:**
- Add method `get_post_context(post_id)` to PixelfedAPIClient
- Uses endpoint: `/api/v1/statuses/{post_id}/context`
- Returns dict with `descendants` array (all replies/comments)
- Parses each comment for: id, account.id, account.username, account.display_name, content, created_at, in_reply_to_id
- Logs number of comments fetched
- Handles empty comment threads (returns empty list)

**Files to modify:**
- `analytics_pixelfed/pixelfed_client.py`

**Method signature:**
```python
def get_post_context(self, post_id):
    """
    Fetch comment thread for a post.

    Returns:
        List of comment dicts with threading info
    """
    endpoint = f"/v1/statuses/{post_id}/context"
    response = self._make_request(endpoint)

    comments = []
    for comment in response.get('descendants', []):
        comments.append({
            'id': comment['id'],
            'account_id': comment['account']['id'],
            'username': comment['account']['username'],
            'display_name': comment['account'].get('display_name', ''),
            'content': comment['content'],
            'created_at': comment['created_at'],
            'in_reply_to_id': comment.get('in_reply_to_id'),
        })

    return comments
```

---

### US-4.5: Implement Fetch Post Shares Method
**As a** developer
**I want to** fetch all accounts who shared/reblogged a post
**So that** I can track virality

**Acceptance Criteria:**
- Add method `get_post_reblogged_by(post_id, max_id=None, limit=80)` to PixelfedAPIClient
- Uses endpoint: `/api/v1/statuses/{post_id}/reblogged_by`
- Handles pagination similar to favourited_by
- Returns list of account dicts
- Fetches ALL pages
- Logs total shares fetched

**Files to modify:**
- `analytics_pixelfed/pixelfed_client.py`

**Method signature:**
```python
def get_post_reblogged_by(self, post_id, max_id=None, limit=80):
    """
    Fetch all accounts who reblogged/shared a post.
    Handles pagination automatically.
    """
```

---

### US-4.6: Add API Client Tests
**As a** developer
**I want to** write tests for Pixelfed API client
**So that** API integration is reliable

**Acceptance Criteria:**
- Create `analytics_pixelfed/tests/test_pixelfed_client.py`
- Use `responses` library to mock HTTP requests
- Test cases:
  - Test client initialization and URL normalization
  - Test successful post fetch with media
  - Test pagination for account posts
  - Test fetch likes (favourited_by)
  - Test fetch comments (context)
  - Test fetch shares (reblogged_by)
  - Test error handling (404, 500, timeout)
  - Test retry logic on transient failures
  - Test rate limiting (verify sleep calls)
- All tests pass: `uv run pytest analytics_pixelfed/tests/test_pixelfed_client.py -v`
- Target: >90% code coverage for pixelfed_client.py

**Files to create:**
- `analytics_pixelfed/tests/test_pixelfed_client.py`

**Test structure:**
```python
import responses
import pytest
from analytics_pixelfed.pixelfed_client import PixelfedAPIClient, PixelfedAPIError

@pytest.fixture
def client():
    return PixelfedAPIClient(
        instance_url="https://pixelfed.social",
        access_token="test_token"
    )

@responses.activate
def test_get_account_posts_success(client):
    # Mock API response
    # Assert correct behavior
    pass

@responses.activate
def test_get_post_favourited_by_pagination(client):
    # Test pagination handling
    pass
```

---

## Phase 5: Implement Analytics Fetcher Service

### US-5.1: Create Analytics Fetcher Service
**As a** developer
**I want to** create a service that orchestrates analytics fetching
**So that** I can reuse logic in tasks and management commands

**Acceptance Criteria:**
- Create `analytics_pixelfed/services.py`
- Implement `PixelfedAnalyticsFetcher` class
- Constructor accepts `account` (MastodonAccount instance)
- Initializes PixelfedAPIClient with account credentials
- Add method `sync_account_posts(limit=40, max_posts=100)`:
  - Fetches posts from account using client
  - Creates/updates PixelfedPost records
  - Links to ScheduledPost if matching caption and timestamp (within 5 min)
  - Returns dict: {posts_synced: int, posts_created: int, posts_updated: int}
- Add comprehensive logging
- Handle API errors gracefully (log and continue)

**Files to create:**
- `analytics_pixelfed/services.py`

**Class structure:**
```python
import logging
from datetime import datetime, timedelta
from django.utils import timezone
from .pixelfed_client import PixelfedAPIClient, PixelfedAPIError
from .models import PixelfedPost
from pixelfed.models import MastodonAccount
from postflow.models import ScheduledPost

logger = logging.getLogger('postflow')

class PixelfedAnalyticsFetcher:
    def __init__(self, account: MastodonAccount):
        self.account = account
        self.client = PixelfedAPIClient(
            instance_url=account.instance_url,
            access_token=account.access_token
        )

    def sync_account_posts(self, limit=40, max_posts=100):
        """
        Sync posts with media from Pixelfed account.

        Args:
            limit: Posts per API request
            max_posts: Maximum total posts to sync

        Returns:
            Dict with sync statistics
        """
        pass
```

**Post matching logic:**
```python
# Try to find matching ScheduledPost
scheduled_post = None
if post_caption:
    # Look for ScheduledPost with same caption posted within 5 minutes
    post_time = parse_datetime(post_data['created_at'])
    scheduled_post = ScheduledPost.objects.filter(
        user=self.account.user,
        caption__iexact=post_caption.strip(),
        scheduled_time__range=(
            post_time - timedelta(minutes=5),
            post_time + timedelta(minutes=5)
        ),
        pixelfed_post_id=post_data['id']
    ).first()
```

---

### US-5.2: Implement Fetch Post Engagement Method
**As a** developer
**I want to** fetch engagement for a specific post
**So that** I can update likes, comments, shares

**Acceptance Criteria:**
- Add method `fetch_post_engagement(pixelfed_post: PixelfedPost)` to PixelfedAnalyticsFetcher
- Fetches likes, comments, shares using API client
- Creates/updates PixelfedLike records (uses get_or_create on post + account_id)
- Creates/updates PixelfedComment records (uses get_or_create on comment_id)
- Creates/updates PixelfedShare records (uses get_or_create on post + account_id)
- After updating, calls `pixelfed_post.refresh_engagement_summary()`
- Returns dict: {new_likes: int, new_comments: int, new_shares: int, total_engagement: int}
- Uses bulk_create when possible for performance
- Logs engagement stats

**Files to modify:**
- `analytics_pixelfed/services.py`

**Method signature:**
```python
def fetch_post_engagement(self, pixelfed_post: PixelfedPost):
    """
    Fetch and update engagement metrics for a post.

    Returns:
        Dict with engagement update stats
    """
    from .models import PixelfedLike, PixelfedComment, PixelfedShare
    from django.utils.dateparse import parse_datetime

    stats = {
        'new_likes': 0,
        'new_comments': 0,
        'new_shares': 0,
        'total_engagement': 0,
    }

    # Fetch likes
    try:
        likes = self.client.get_post_favourited_by(pixelfed_post.pixelfed_post_id)
        for like_data in likes:
            _, created = PixelfedLike.objects.get_or_create(
                post=pixelfed_post,
                account_id=like_data['id'],
                defaults={
                    'username': like_data['username'],
                    'display_name': like_data.get('display_name', ''),
                    'liked_at': timezone.now(),  # Approximate timestamp
                }
            )
            if created:
                stats['new_likes'] += 1
    except PixelfedAPIError as e:
        logger.error(f"Error fetching likes for {pixelfed_post.pixelfed_post_id}: {e}")

    # Similar for comments and shares...

    # Update summary
    pixelfed_post.refresh_engagement_summary()
    stats['total_engagement'] = pixelfed_post.engagement_summary.total_engagement

    return stats
```

---

### US-5.3: Implement Batch Fetch for Multiple Posts
**As a** developer
**I want to** fetch engagement for multiple posts efficiently
**So that** hourly tasks complete quickly

**Acceptance Criteria:**
- Add method `fetch_recent_posts_engagement(hours=24, max_posts=50)` to PixelfedAnalyticsFetcher
- Queries PixelfedPost for account's recent posts
- Calls `fetch_post_engagement()` for each post
- Sleeps 2 seconds between posts (rate limiting)
- Aggregates statistics across all posts
- Returns dict: {posts_processed: int, total_new_likes: int, total_new_comments: int, total_new_shares: int, errors: int}
- Logs progress every 10 posts

**Files to modify:**
- `analytics_pixelfed/services.py`

**Method signature:**
```python
def fetch_recent_posts_engagement(self, hours=24, max_posts=50):
    """
    Fetch engagement for recent posts from this account.

    Args:
        hours: Fetch posts from last N hours
        max_posts: Maximum posts to process

    Returns:
        Aggregated statistics dict
    """
    from datetime import timedelta
    from django.utils import timezone
    from time import sleep

    cutoff_time = timezone.now() - timedelta(hours=hours)
    recent_posts = PixelfedPost.objects.filter(
        account=self.account,
        posted_at__gte=cutoff_time
    ).order_by('-posted_at')[:max_posts]

    # Process each post...
```

---

### US-5.4: Add Service Tests
**As a** developer
**I want to** write tests for analytics fetcher service
**So that** business logic is reliable

**Acceptance Criteria:**
- Create `analytics_pixelfed/tests/test_services.py`
- Mock PixelfedAPIClient methods
- Test cases:
  - Test sync_account_posts creates PixelfedPost records
  - Test sync_account_posts links to ScheduledPost when matching
  - Test fetch_post_engagement creates Like/Comment/Share records
  - Test fetch_post_engagement updates engagement summary
  - Test fetch_recent_posts_engagement processes multiple posts
  - Test error handling when API fails
  - Test duplicate handling (get_or_create logic)
- Use pytest fixtures for test data (PixelfedPost, MastodonAccount)
- All tests pass with >90% coverage

**Files to create:**
- `analytics_pixelfed/tests/test_services.py`

**Test structure:**
```python
import pytest
from unittest.mock import Mock, patch
from analytics_pixelfed.services import PixelfedAnalyticsFetcher
from analytics_pixelfed.models import PixelfedPost, PixelfedLike
from pixelfed.models import MastodonAccount

@pytest.fixture
def pixelfed_account(db):
    # Create test MastodonAccount
    pass

@pytest.fixture
def fetcher(pixelfed_account):
    return PixelfedAnalyticsFetcher(pixelfed_account)

@patch('analytics_pixelfed.services.PixelfedAPIClient')
def test_sync_account_posts(mock_client, fetcher):
    # Mock API responses
    # Call sync_account_posts
    # Assert PixelfedPost created
    pass
```

---

## Phase 6: Create Management Commands

### US-6.1: Create Sync Posts Management Command
**As a** developer
**I want to** create a command to sync posts from Pixelfed
**So that** I can manually populate the database

**Acceptance Criteria:**
- Create `analytics_pixelfed/management/commands/sync_pixelfed_posts.py`
- Command: `python manage.py sync_pixelfed_posts`
- Options:
  - `--account-id <id>` - sync specific account
  - `--all` - sync all connected Pixelfed accounts
  - `--limit <n>` - posts per request (default: 40)
  - `--max-posts <n>` - max total posts (default: 100)
- For each account, creates PixelfedAnalyticsFetcher and calls sync_account_posts()
- Displays progress with styled output
- Shows summary: accounts processed, posts synced, errors
- Handles errors gracefully (continues with next account)

**Files to create:**
- `analytics_pixelfed/management/commands/sync_pixelfed_posts.py`

**Command structure:**
```python
from django.core.management.base import BaseCommand
from pixelfed.models import MastodonAccount
from analytics_pixelfed.services import PixelfedAnalyticsFetcher
import logging

logger = logging.getLogger('postflow')

class Command(BaseCommand):
    help = 'Sync posts with media from connected Pixelfed accounts'

    def add_arguments(self, parser):
        parser.add_argument('--account-id', type=int, help='Specific account ID')
        parser.add_argument('--all', action='store_true', help='Sync all accounts')
        parser.add_argument('--limit', type=int, default=40)
        parser.add_argument('--max-posts', type=int, default=100)

    def handle(self, *args, **options):
        # Implementation
        pass
```

**Output formatting:**
```python
self.stdout.write(self.style.SUCCESS(f'✓ Synced {stats["posts_synced"]} posts'))
self.stdout.write(self.style.WARNING(f'⚠ {errors} errors'))
```

---

### US-6.2: Create Fetch Engagement Management Command
**As a** developer
**I want to** create a command to fetch engagement metrics
**So that** I can manually update analytics

**Acceptance Criteria:**
- Create `analytics_pixelfed/management/commands/fetch_pixelfed_engagement.py`
- Command: `python manage.py fetch_pixelfed_engagement`
- Options:
  - `--post-id <id>` - fetch specific post
  - `--account-id <id>` - fetch for account's recent posts
  - `--all` - fetch for all accounts
  - `--hours <n>` - posts from last N hours (default: 24)
  - `--max-posts <n>` - max posts per account (default: 50)
- Uses PixelfedAnalyticsFetcher service
- Shows progress and statistics
- Handles errors gracefully

**Files to create:**
- `analytics_pixelfed/management/commands/fetch_pixelfed_engagement.py`

**Command logic:**
```python
class Command(BaseCommand):
    help = 'Fetch engagement metrics for Pixelfed posts'

    def handle(self, *args, **options):
        if options['post_id']:
            # Fetch single post
            post = PixelfedPost.objects.get(id=options['post_id'])
            fetcher = PixelfedAnalyticsFetcher(post.account)
            stats = fetcher.fetch_post_engagement(post)
            self.stdout.write(f"Fetched {stats['total_engagement']} engagements")

        elif options['account_id']:
            # Fetch account's recent posts
            account = MastodonAccount.objects.get(id=options['account_id'])
            fetcher = PixelfedAnalyticsFetcher(account)
            stats = fetcher.fetch_recent_posts_engagement(
                hours=options['hours'],
                max_posts=options['max_posts']
            )
            # Display stats

        elif options['all']:
            # Fetch all accounts
            pass
```

---

## Phase 7: Implement Background Tasks with django-tasks

### US-7.1: Create Hourly Engagement Fetch Task
**As a** developer
**I want to** create a task that fetches engagement every hour
**So that** analytics stay up-to-date automatically

**Acceptance Criteria:**
- Create `analytics_pixelfed/tasks.py`
- Implement function `fetch_all_pixelfed_engagement()`:
  - Gets all connected Pixelfed accounts (MastodonAccount where instance_url contains 'pixelfed')
  - For each account, creates fetcher and calls `fetch_recent_posts_engagement(hours=24, max_posts=30)`
  - Sleeps 5 seconds between accounts (rate limiting)
  - Aggregates statistics
  - Logs summary
  - Returns dict with stats
- Add error handling - continue with other accounts if one fails
- Max execution time: 10 minutes
- Add logging throughout

**Files to create:**
- `analytics_pixelfed/tasks.py`

**Task function:**
```python
import logging
from time import sleep
from pixelfed.models import MastodonAccount
from .services import PixelfedAnalyticsFetcher

logger = logging.getLogger('postflow')

def fetch_all_pixelfed_engagement():
    """
    Background task to fetch engagement for all Pixelfed accounts.
    Runs hourly via django-tasks.

    Returns:
        Dict with aggregated statistics
    """
    logger.info("Starting hourly Pixelfed engagement fetch")

    # Get Pixelfed accounts (filter by instance_url containing 'pixelfed')
    pixelfed_accounts = MastodonAccount.objects.filter(
        instance_url__icontains='pixelfed'
    )

    total_stats = {
        'accounts_processed': 0,
        'posts_processed': 0,
        'total_new_likes': 0,
        'total_new_comments': 0,
        'total_new_shares': 0,
        'errors': 0,
    }

    for account in pixelfed_accounts:
        try:
            logger.info(f"Fetching engagement for @{account.username}")
            fetcher = PixelfedAnalyticsFetcher(account)
            stats = fetcher.fetch_recent_posts_engagement(hours=24, max_posts=30)

            # Aggregate stats
            total_stats['accounts_processed'] += 1
            total_stats['posts_processed'] += stats['posts_processed']
            total_stats['total_new_likes'] += stats['total_new_likes']
            total_stats['total_new_comments'] += stats['total_new_comments']
            total_stats['total_new_shares'] += stats['total_new_shares']

            sleep(5)  # Rate limiting between accounts

        except Exception as e:
            logger.error(f"Error fetching engagement for {account.username}: {e}")
            total_stats['errors'] += 1

    logger.info(f"Hourly fetch complete: {total_stats}")
    return total_stats
```

---

### US-7.2: Register Task with django-tasks
**As a** developer
**I want to** register the engagement task with django-tasks
**So that** it can be scheduled and monitored

**Acceptance Criteria:**
- Update `analytics_pixelfed/tasks.py`
- Import `task` decorator from django_tasks
- Decorate `fetch_all_pixelfed_engagement` with `@task`
- Configure task options:
  - `queue_name='default'`
  - `priority=5` (medium priority)
  - `max_retries=2`
  - `retry_delay=300` (5 minutes between retries)
- Task should appear in django-tasks registry
- Test task execution: `tasks.enqueue(fetch_all_pixelfed_engagement)`

**Files to modify:**
- `analytics_pixelfed/tasks.py`

**Task decoration:**
```python
from django_tasks import task

@task(
    queue_name='default',
    priority=5,
    max_retries=2,
    retry_delay=300,
)
def fetch_all_pixelfed_engagement():
    """Background task for hourly engagement fetch"""
    # Implementation from US-7.1
```

**Test in shell:**
```python
from analytics_pixelfed.tasks import fetch_all_pixelfed_engagement
from django_tasks import tasks

# Enqueue task
result = tasks.enqueue(fetch_all_pixelfed_engagement)
print(f"Task enqueued: {result.id}")
```

---

### US-7.3: Create Hourly Task Scheduler
**As a** developer
**I want to** schedule the engagement task to run every hour
**So that** analytics update automatically

**Acceptance Criteria:**
- Create `analytics_pixelfed/management/commands/schedule_pixelfed_analytics.py`
- Command schedules `fetch_all_pixelfed_engagement` task
- Uses django-tasks' scheduling API (if available) or creates cron-like schedule
- Schedule: every hour at minute 0 (1:00, 2:00, 3:00, etc.)
- Command is idempotent - can run multiple times without duplicating schedules
- Option `--clear` removes existing schedule
- Displays confirmation message

**Files to create:**
- `analytics_pixelfed/management/commands/schedule_pixelfed_analytics.py`

**Command implementation:**
```python
from django.core.management.base import BaseCommand
from django_tasks import tasks
from analytics_pixelfed.tasks import fetch_all_pixelfed_engagement

class Command(BaseCommand):
    help = 'Schedule hourly Pixelfed analytics fetching'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Remove existing schedule')

    def handle(self, *args, **options):
        if options['clear']:
            # Clear existing schedules
            # Implementation depends on django-tasks API
            self.stdout.write(self.style.SUCCESS('Cleared existing schedules'))
            return

        # Schedule task to run hourly
        # Note: Exact implementation depends on django-tasks scheduling API
        # May use APScheduler integration or built-in scheduler

        self.stdout.write(self.style.SUCCESS(
            'Scheduled Pixelfed analytics to run every hour'
        ))
```

**Note:** If django-tasks doesn't have built-in scheduling, integrate with APScheduler:
```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()
scheduler.add_job(
    func=lambda: tasks.enqueue(fetch_all_pixelfed_engagement),
    trigger=CronTrigger(minute=0),  # Every hour
    id='pixelfed_analytics',
    replace_existing=True,
)
scheduler.start()
```

---

### US-7.4: Auto-Schedule on App Ready
**As a** developer
**I want to** automatically schedule the task when Django starts
**So that** I don't need to manually run schedule command

**Acceptance Criteria:**
- Update `analytics_pixelfed/apps.py`
- Override `ready()` method in AnalyticsPixelfedConfig
- Check if schedule already exists (avoid duplicates)
- If not exists or in development (DEBUG=True), create schedule
- Respect environment variable `SKIP_AUTO_SCHEDULE=1` (for tests)
- Don't run during migrations: check `sys.argv`
- Log when schedule is created
- Handle errors gracefully (log warning, don't crash)

**Files to modify:**
- `analytics_pixelfed/apps.py`

**App config implementation:**
```python
import sys
import logging
from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger('postflow')

class AnalyticsPixelfedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics_pixelfed'
    verbose_name = 'Pixelfed Analytics'

    def ready(self):
        # Don't run during migrations or if explicitly disabled
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return

        if os.environ.get('SKIP_AUTO_SCHEDULE') == '1':
            logger.info("Skipping auto-schedule (SKIP_AUTO_SCHEDULE=1)")
            return

        try:
            # Import here to avoid AppRegistryNotReady
            from .tasks import fetch_all_pixelfed_engagement
            from django_tasks import tasks

            # Check if schedule exists, create if not
            # Implementation depends on django-tasks API

            logger.info("Pixelfed analytics scheduled successfully")

        except Exception as e:
            logger.warning(f"Could not auto-schedule Pixelfed analytics: {e}")
```

---

## Phase 8: Create Unified Analytics Dashboard

### US-8.1: Create Pixelfed Analytics Dashboard View
**As a** developer
**I want to** create a dashboard showing Pixelfed post analytics
**So that** users can see engagement metrics

**Acceptance Criteria:**
- Create view `pixelfed_dashboard(request)` in `analytics_pixelfed/views.py`
- Login required decorator
- Shows user's PixelfedPost records from connected accounts
- Displays: post image, caption (truncated), posted date, engagement summary
- Filters:
  - Date range: last 7, 30, 90 days (query param `days`, default=30)
  - Sort by: most likes, most comments, most shares, most recent (query param `sort`, default='-posted_at')
- Pagination: 20 posts per page
- Generate signed URLs for media if using S3
- Add "Refresh" button (HTMX) to trigger manual fetch
- Template: `analytics_pixelfed/templates/analytics_pixelfed/dashboard.html`

**Files to create:**
- `analytics_pixelfed/views.py`
- `analytics_pixelfed/templates/analytics_pixelfed/dashboard.html`

**View implementation:**
```python
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from .models import PixelfedPost
from pixelfed.models import MastodonAccount

@login_required
def pixelfed_dashboard(request):
    # Get filter parameters
    days = int(request.GET.get('days', 30))
    sort = request.GET.get('sort', '-posted_at')

    # Get user's Pixelfed accounts
    user_accounts = MastodonAccount.objects.filter(
        user=request.user,
        instance_url__icontains='pixelfed'
    )

    # Query posts
    cutoff_date = timezone.now() - timedelta(days=days)
    posts = PixelfedPost.objects.filter(
        account__in=user_accounts,
        posted_at__gte=cutoff_date
    ).select_related('engagement_summary', 'account').order_by(sort)

    # Paginate
    paginator = Paginator(posts, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'days': days,
        'sort': sort,
        'total_posts': posts.count(),
    }

    return render(request, 'analytics_pixelfed/dashboard.html', context)
```

**Template structure (simplified):**
```html
{% extends "base.html" %}

{% block content %}
<div class="container">
  <h1>Pixelfed Analytics</h1>

  <!-- Filters -->
  <div class="filters">
    <select name="days" hx-get="{% url 'analytics_pixelfed:dashboard' %}" hx-target="#posts-grid">
      <option value="7">Last 7 days</option>
      <option value="30" selected>Last 30 days</option>
      <option value="90">Last 90 days</option>
    </select>

    <button hx-post="{% url 'analytics_pixelfed:refresh' %}" hx-indicator="#spinner">
      Refresh Analytics
    </button>
  </div>

  <!-- Posts Grid -->
  <div id="posts-grid" class="grid">
    {% for post in page_obj %}
    <div class="post-card">
      <img src="{{ post.media_url }}" alt="Post image">
      <p>{{ post.caption|truncatewords:20 }}</p>
      <div class="engagement">
        <span>❤️ {{ post.engagement_summary.total_likes }}</span>
        <span>💬 {{ post.engagement_summary.total_comments }}</span>
        <span>🔄 {{ post.engagement_summary.total_shares }}</span>
      </div>
      <a href="{% url 'analytics_pixelfed:post_detail' post.id %}">View Details</a>
    </div>
    {% endfor %}
  </div>

  <!-- Pagination -->
  {% if page_obj.has_other_pages %}
  <div class="pagination">
    <!-- Pagination links -->
  </div>
  {% endif %}
</div>
{% endblock %}
```

---

### US-8.2: Create Post Detail View with Engagement Timeline
**As a** developer
**I want to** create a detailed view for individual posts
**So that** users can see granular engagement data

**Acceptance Criteria:**
- Create view `post_detail(request, post_id)` in `analytics_pixelfed/views.py`
- Login required, access control (user must own the post's account)
- Shows PixelfedPost details: image, caption, posted date, post URL
- Three sections:
  1. **Engagement Overview**: total counts, engagement chart (future)
  2. **Likes**: table with username, display_name, liked_at timestamp
  3. **Comments**: threaded comment display with content and timestamps
  4. **Shares**: table with username, display_name, shared_at
- Pagination for likes/comments/shares (20 per page)
- Button to manually refresh this post's engagement
- Template: `analytics_pixelfed/templates/analytics_pixelfed/post_detail.html`

**Files to modify:**
- `analytics_pixelfed/views.py`

**View implementation:**
```python
@login_required
def post_detail(request, post_id):
    from django.shortcuts import get_object_or_404
    from django.http import HttpResponseForbidden

    post = get_object_or_404(
        PixelfedPost.objects.select_related('engagement_summary', 'account'),
        id=post_id
    )

    # Access control
    if post.account.user != request.user:
        return HttpResponseForbidden("You don't have access to this post")

    # Get engagement data
    likes = post.likes.all().order_by('-liked_at')[:100]
    comments = post.comments.all().order_by('commented_at')[:100]
    shares = post.shares.all().order_by('-shared_at')[:100]

    context = {
        'post': post,
        'likes': likes,
        'comments': comments,
        'shares': shares,
    }

    return render(request, 'analytics_pixelfed/post_detail.html', context)
```

---

### US-8.3: Create Manual Refresh Endpoint
**As a** developer
**I want to** create an endpoint to manually trigger analytics refresh
**So that** users can get latest data on demand

**Acceptance Criteria:**
- Create view `refresh_analytics(request)` in `analytics_pixelfed/views.py`
- POST only, login required
- Accepts optional query param `post_id`
- If `post_id`: enqueue task to fetch that post's engagement
- If no `post_id`: enqueue task to fetch all user's Pixelfed accounts
- Returns JSON: `{'status': 'success', 'message': 'Analytics refresh started', 'task_id': <id>}`
- Rate limiting: max 1 request per minute per user (use Django cache or simple timestamp check)
- Returns 429 if rate limited

**Files to modify:**
- `analytics_pixelfed/views.py`

**View implementation:**
```python
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django_tasks import tasks
from .tasks import fetch_all_pixelfed_engagement

@login_required
@require_POST
def refresh_analytics(request):
    # Rate limiting
    cache_key = f'analytics_refresh_{request.user.id}'
    if cache.get(cache_key):
        return JsonResponse({
            'status': 'error',
            'message': 'Please wait before refreshing again'
        }, status=429)

    # Set rate limit (60 seconds)
    cache.set(cache_key, True, 60)

    # Enqueue task
    try:
        task_result = tasks.enqueue(fetch_all_pixelfed_engagement)

        return JsonResponse({
            'status': 'success',
            'message': 'Analytics refresh started',
            'task_id': str(task_result.id),
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
```

---

### US-8.4: Create URL Routes for Pixelfed Analytics
**As a** developer
**I want to** define URL patterns for Pixelfed analytics views
**So that** users can access the dashboard

**Acceptance Criteria:**
- Update `analytics_pixelfed/urls.py`
- Define URL patterns:
  - `''` → `pixelfed_dashboard` (name='dashboard')
  - `'post/<int:post_id>/'` → `post_detail` (name='post_detail')
  - `'refresh/'` → `refresh_analytics` (name='refresh')
- Set `app_name = 'analytics_pixelfed'`
- Include in main urls.py: `path('analytics/pixelfed/', include('analytics_pixelfed.urls'))`

**Files to modify:**
- `analytics_pixelfed/urls.py`
- `core/urls.py`

**URL configuration:**
```python
# analytics_pixelfed/urls.py
from django.urls import path
from . import views

app_name = 'analytics_pixelfed'

urlpatterns = [
    path('', views.pixelfed_dashboard, name='dashboard'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('refresh/', views.refresh_analytics, name='refresh'),
]
```

```python
# core/urls.py (add to urlpatterns)
path('analytics/pixelfed/', include('analytics_pixelfed.urls')),
```

---

## Phase 9: Create Cross-Platform Analytics Core

### US-9.1: Create Analytics Core App
**As a** developer
**I want to** create a core analytics app for cross-platform features
**So that** users can compare performance across platforms

**Acceptance Criteria:**
- Run `uv run manage.py startapp analytics_core`
- Add `analytics_core` to `INSTALLED_APPS` (after analytics_pixelfed)
- This app will contain:
  - Unified dashboard showing all platforms
  - Cross-platform comparison views
  - Aggregated statistics models (future)
  - Data visualization utilities (future)
- Create basic directory structure
- Verify app recognized: `uv run manage.py check`

**Files to create:**
- `analytics_core/__init__.py`
- `analytics_core/apps.py`
- `analytics_core/views.py`
- `analytics_core/urls.py`
- `analytics_core/templates/analytics_core/`

**Files to modify:**
- `core/settings.py` - add to INSTALLED_APPS

---

### US-9.2: Create Unified Analytics Dashboard
**As a** developer
**I want to** create a unified dashboard showing all platforms
**So that** users can see engagement across Pixelfed, Instagram, Mastodon

**Acceptance Criteria:**
- Create view `unified_dashboard(request)` in `analytics_core/views.py`
- Login required
- Shows posts from ALL platforms (currently just Pixelfed, future: Instagram, Mastodon)
- Displays: platform badge, post image, caption, engagement metrics
- Filters:
  - Platform: all, pixelfed, instagram, mastodon
  - Date range: 7, 30, 90 days
  - Sort by: most engagement, most recent
- Each post card shows platform-specific engagement summary
- Click post → go to platform-specific detail view
- Template: `analytics_core/templates/analytics_core/unified_dashboard.html`

**Files to create:**
- `analytics_core/views.py`
- `analytics_core/templates/analytics_core/unified_dashboard.html`

**View implementation:**
```python
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from analytics_pixelfed.models import PixelfedPost
# Future: from analytics_instagram.models import InstagramPost
# Future: from analytics_mastodon.models import MastodonPost

@login_required
def unified_dashboard(request):
    days = int(request.GET.get('days', 30))
    platform = request.GET.get('platform', 'all')

    cutoff_date = timezone.now() - timedelta(days=days)

    # Aggregate posts from all platforms
    all_posts = []

    # Pixelfed posts
    if platform in ['all', 'pixelfed']:
        pixelfed_posts = PixelfedPost.objects.filter(
            account__user=request.user,
            posted_at__gte=cutoff_date
        ).select_related('engagement_summary')

        for post in pixelfed_posts:
            all_posts.append({
                'platform': 'pixelfed',
                'post': post,
                'image_url': post.media_url,
                'caption': post.caption,
                'posted_at': post.posted_at,
                'total_engagement': post.engagement_summary.total_engagement if hasattr(post, 'engagement_summary') else 0,
                'likes': post.engagement_summary.total_likes if hasattr(post, 'engagement_summary') else 0,
                'comments': post.engagement_summary.total_comments if hasattr(post, 'engagement_summary') else 0,
                'shares': post.engagement_summary.total_shares if hasattr(post, 'engagement_summary') else 0,
                'detail_url': f'/analytics/pixelfed/post/{post.id}/',
            })

    # Future: Add Instagram posts
    # Future: Add Mastodon posts

    # Sort by engagement or date
    sort = request.GET.get('sort', '-posted_at')
    if sort == '-engagement':
        all_posts.sort(key=lambda x: x['total_engagement'], reverse=True)
    else:
        all_posts.sort(key=lambda x: x['posted_at'], reverse=True)

    context = {
        'posts': all_posts,
        'days': days,
        'platform': platform,
        'total_posts': len(all_posts),
    }

    return render(request, 'analytics_core/unified_dashboard.html', context)
```

**Template design:**
- Platform badge color-coded (Pixelfed=pink, Instagram=gradient, Mastodon=purple)
- Responsive grid layout
- HTMX for filtering without page reload

---

### US-9.3: Create Platform Comparison View
**As a** developer
**I want to** create a comparison view showing platform performance
**So that** users can see which platform performs best

**Acceptance Criteria:**
- Create view `platform_comparison(request)` in `analytics_core/views.py`
- Shows aggregate statistics per platform:
  - Total posts
  - Total engagement (likes + comments + shares)
  - Average engagement per post
  - Most liked post
  - Most commented post
  - Posting frequency
- Bar chart comparing engagement (future: use Chart.js or similar)
- Table with detailed breakdown
- Date range filter
- Template: `analytics_core/templates/analytics_core/platform_comparison.html`

**Files to modify:**
- `analytics_core/views.py`

**View logic:**
```python
from django.db.models import Count, Sum, Avg

@login_required
def platform_comparison(request):
    days = int(request.GET.get('days', 30))
    cutoff_date = timezone.now() - timedelta(days=days)

    platform_stats = {}

    # Pixelfed stats
    pixelfed_posts = PixelfedPost.objects.filter(
        account__user=request.user,
        posted_at__gte=cutoff_date
    ).select_related('engagement_summary')

    if pixelfed_posts.exists():
        total_engagement = sum(
            p.engagement_summary.total_engagement
            for p in pixelfed_posts
            if hasattr(p, 'engagement_summary')
        )

        platform_stats['pixelfed'] = {
            'total_posts': pixelfed_posts.count(),
            'total_engagement': total_engagement,
            'avg_engagement': total_engagement / pixelfed_posts.count() if pixelfed_posts.count() > 0 else 0,
            'most_liked': pixelfed_posts.order_by('-engagement_summary__total_likes').first(),
        }

    # Future: Add Instagram and Mastodon stats

    context = {
        'platform_stats': platform_stats,
        'days': days,
    }

    return render(request, 'analytics_core/platform_comparison.html', context)
```

---

### US-9.4: Create Analytics Core URL Routes
**As a** developer
**I want to** define URL patterns for core analytics views
**So that** users can access unified features

**Acceptance Criteria:**
- Update `analytics_core/urls.py`
- Define URL patterns:
  - `''` → `unified_dashboard` (name='unified_dashboard')
  - `'comparison/'` → `platform_comparison` (name='platform_comparison')
- Include in main urls.py: `path('analytics/', include('analytics_core.urls'))`
- Update `analytics/urls.py` to redirect to core (or keep old routes for backward compat)

**Files to modify:**
- `analytics_core/urls.py`
- `core/urls.py`

**URL configuration:**
```python
# analytics_core/urls.py
from django.urls import path
from . import views

app_name = 'analytics_core'

urlpatterns = [
    path('', views.unified_dashboard, name='unified_dashboard'),
    path('comparison/', views.platform_comparison, name='platform_comparison'),
]
```

```python
# core/urls.py (modify existing analytics path)
path('analytics/', include('analytics_core.urls')),
```

---

## Phase 10: Data Visualization

### US-10.1: Install Chart.js via CDN
**As a** developer
**I want to** add Chart.js for data visualization
**So that** I can display engagement charts

**Acceptance Criteria:**
- Add Chart.js CDN link to base template or analytics templates
- Create base chart template partial: `analytics_core/templates/analytics_core/partials/chart_base.html`
- Test basic chart rendering on dashboard
- Use Chart.js v4.x (latest stable)

**Files to modify:**
- `analytics_core/templates/analytics_core/unified_dashboard.html`
- Create `analytics_core/templates/analytics_core/partials/chart_base.html`

**Template snippet:**
```html
<!-- In head -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>

<!-- Chart container -->
<canvas id="engagementChart" width="400" height="200"></canvas>

<script>
const ctx = document.getElementById('engagementChart');
new Chart(ctx, {
  type: 'bar',
  data: {
    labels: ['Pixelfed', 'Instagram', 'Mastodon'],
    datasets: [{
      label: 'Total Engagement',
      data: [{{ pixelfed_engagement }}, {{ instagram_engagement }}, {{ mastodon_engagement }}],
      backgroundColor: ['#ec4899', '#f59e0b', '#8b5cf6'],
    }]
  },
  options: {
    responsive: true,
  }
});
</script>
```

---

### US-10.2: Create Engagement Timeline Chart
**As a** developer
**I want to** display engagement over time on post detail view
**So that** users can see engagement velocity

**Acceptance Criteria:**
- Add method `get_engagement_timeline(post, days=7)` to analytics_core/utils.py
- Groups likes/comments/shares by day
- Returns data structure for Chart.js line chart
- Add chart to post_detail template
- Shows engagement accumulation over time since posting

**Files to create:**
- `analytics_core/utils.py`

**Files to modify:**
- `analytics_pixelfed/views.py` (post_detail)
- `analytics_pixelfed/templates/analytics_pixelfed/post_detail.html`

**Utility function:**
```python
from django.db.models import Count
from django.db.models.functions import TruncDate
from datetime import timedelta

def get_engagement_timeline(post, days=7):
    """
    Get engagement counts grouped by day.

    Args:
        post: PixelfedPost instance
        days: Number of days from post date

    Returns:
        Dict with labels and datasets for Chart.js
    """
    from analytics_pixelfed.models import PixelfedLike, PixelfedComment, PixelfedShare

    start_date = post.posted_at
    end_date = start_date + timedelta(days=days)

    # Group likes by day
    likes_by_day = PixelfedLike.objects.filter(
        post=post,
        liked_at__gte=start_date,
        liked_at__lte=end_date
    ).annotate(day=TruncDate('liked_at')).values('day').annotate(count=Count('id')).order_by('day')

    # Similar for comments and shares...

    # Format for Chart.js
    labels = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days+1)]

    return {
        'labels': labels,
        'datasets': [
            {'label': 'Likes', 'data': [...]},
            {'label': 'Comments', 'data': [...]},
            {'label': 'Shares', 'data': [...]},
        ]
    }
```

---

### US-10.3: Create Platform Comparison Bar Chart
**As a** developer
**I want to** display bar chart on comparison view
**So that** users can visually compare platform performance

**Acceptance Criteria:**
- Update `platform_comparison` view to prepare chart data
- Add Chart.js bar chart to template
- X-axis: platforms (Pixelfed, Instagram, Mastodon)
- Y-axis: engagement metrics
- Multiple bars per platform: likes, comments, shares
- Color-coded by platform theme

**Files to modify:**
- `analytics_core/views.py` (platform_comparison)
- `analytics_core/templates/analytics_core/platform_comparison.html`

**Chart data preparation:**
```python
# In view
chart_data = {
    'labels': list(platform_stats.keys()),
    'likes': [stats['total_likes'] for stats in platform_stats.values()],
    'comments': [stats['total_comments'] for stats in platform_stats.values()],
    'shares': [stats['total_shares'] for stats in platform_stats.values()],
}
context['chart_data'] = chart_data
```

**Template chart:**
```html
<canvas id="comparisonChart"></canvas>
<script>
const data = {
  labels: {{ chart_data.labels|safe }},
  datasets: [
    {
      label: 'Likes',
      data: {{ chart_data.likes|safe }},
      backgroundColor: '#ec4899',
    },
    {
      label: 'Comments',
      data: {{ chart_data.comments|safe }},
      backgroundColor: '#3b82f6',
    },
    {
      label: 'Shares',
      data: {{ chart_data.shares|safe }},
      backgroundColor: '#10b981',
    }
  ]
};

new Chart(document.getElementById('comparisonChart'), {
  type: 'bar',
  data: data,
  options: {
    responsive: true,
    scales: {
      y: {
        beginAtZero: true
      }
    }
  }
});
</script>
```

---

## Phase 11: Testing

### US-11.1: Write Model Tests for Pixelfed Analytics
**As a** developer
**I want to** write comprehensive tests for analytics models
**So that** data integrity is ensured

**Acceptance Criteria:**
- Create `analytics_pixelfed/tests/test_models.py`
- Test cases:
  - PixelfedPost creation and validation
  - PixelfedPost.refresh_engagement_summary()
  - PixelfedLike unique constraint (post + account_id)
  - PixelfedComment creation with threading (in_reply_to_id)
  - PixelfedShare unique constraint
  - PixelfedEngagementSummary.update_from_post() calculation
  - Cascade deletion (delete post → deletes likes/comments/shares)
  - Model string representations
  - Helper methods (get_recent_engagement, get_top_likers)
- Use pytest fixtures for test data
- All tests pass: `uv run pytest analytics_pixelfed/tests/test_models.py -v`
- Coverage target: >90%

**Files to create:**
- `analytics_pixelfed/tests/test_models.py`

**Test structure:**
```python
import pytest
from django.utils import timezone
from analytics_pixelfed.models import (
    PixelfedPost, PixelfedLike, PixelfedComment, PixelfedShare, PixelfedEngagementSummary
)
from pixelfed.models import MastodonAccount
from postflow.models import CustomUser

@pytest.fixture
def pixelfed_account(db):
    user = CustomUser.objects.create_user(email='test@example.com', password='pass')
    account = MastodonAccount.objects.create(
        user=user,
        instance_url='https://pixelfed.social',
        username='testuser',
        access_token='token123'
    )
    return account

@pytest.fixture
def pixelfed_post(pixelfed_account):
    post = PixelfedPost.objects.create(
        account=pixelfed_account,
        pixelfed_post_id='12345',
        instance_url='https://pixelfed.social',
        username='testuser',
        caption='Test post',
        media_url='https://example.com/image.jpg',
        media_type='image',
        post_url='https://pixelfed.social/@testuser/12345',
        posted_at=timezone.now()
    )
    return post

@pytest.mark.django_db
def test_pixelfed_post_creation(pixelfed_post):
    assert pixelfed_post.platform == 'pixelfed'
    assert pixelfed_post.pixelfed_post_id == '12345'
    assert str(pixelfed_post) == '@testuser - 12345'

@pytest.mark.django_db
def test_pixelfed_like_unique_constraint(pixelfed_post):
    PixelfedLike.objects.create(
        post=pixelfed_post,
        account_id='user1',
        username='user1',
        liked_at=timezone.now()
    )

    # Duplicate should raise IntegrityError
    with pytest.raises(Exception):
        PixelfedLike.objects.create(
            post=pixelfed_post,
            account_id='user1',
            username='user1',
            liked_at=timezone.now()
        )

@pytest.mark.django_db
def test_engagement_summary_calculation(pixelfed_post):
    # Create engagement
    PixelfedLike.objects.create(post=pixelfed_post, account_id='u1', username='u1', liked_at=timezone.now())
    PixelfedLike.objects.create(post=pixelfed_post, account_id='u2', username='u2', liked_at=timezone.now())
    PixelfedComment.objects.create(
        post=pixelfed_post, comment_id='c1', account_id='u3', username='u3',
        content='Great!', commented_at=timezone.now()
    )

    # Refresh summary
    summary = pixelfed_post.refresh_engagement_summary()

    assert summary.total_likes == 2
    assert summary.total_comments == 1
    assert summary.total_shares == 0
    assert summary.total_engagement == 3
```

---

### US-11.2: Write View Tests for Pixelfed Dashboard
**As a** developer
**I want to** write tests for analytics views
**So that** UI functionality is verified

**Acceptance Criteria:**
- Create `analytics_pixelfed/tests/test_views.py`
- Test cases:
  - Dashboard requires authentication
  - Dashboard displays user's posts only
  - Dashboard filtering by days works
  - Dashboard sorting works
  - Post detail view requires authentication
  - Post detail access control (user can only see own posts)
  - Refresh endpoint works and enqueues task
  - Refresh endpoint rate limiting
  - HTMX requests return correct fragments
- Use Django test client
- Mock django_tasks.enqueue to avoid running actual tasks
- All tests pass with >90% coverage

**Files to create:**
- `analytics_pixelfed/tests/test_views.py`

**Test structure:**
```python
import pytest
from django.urls import reverse
from django.test import Client
from unittest.mock import patch, Mock

@pytest.fixture
def client():
    return Client()

@pytest.fixture
def authenticated_client(pixelfed_account):
    client = Client()
    client.force_login(pixelfed_account.user)
    return client

@pytest.mark.django_db
def test_dashboard_requires_authentication(client):
    url = reverse('analytics_pixelfed:dashboard')
    response = client.get(url)
    assert response.status_code == 302  # Redirect to login

@pytest.mark.django_db
def test_dashboard_displays_posts(authenticated_client, pixelfed_post):
    url = reverse('analytics_pixelfed:dashboard')
    response = authenticated_client.get(url)
    assert response.status_code == 200
    assert pixelfed_post.caption in str(response.content)

@pytest.mark.django_db
@patch('analytics_pixelfed.views.tasks.enqueue')
def test_refresh_endpoint(mock_enqueue, authenticated_client):
    mock_enqueue.return_value = Mock(id='task123')
    url = reverse('analytics_pixelfed:refresh')
    response = authenticated_client.post(url)
    assert response.status_code == 200
    assert mock_enqueue.called
```

---

### US-11.3: Write Integration Tests for Analytics Flow
**As a** developer
**I want to** write end-to-end tests for analytics workflow
**So that** the full system works together

**Acceptance Criteria:**
- Create `analytics_pixelfed/tests/test_integration.py`
- Test scenarios:
  - **Full sync flow**: Mock API → sync posts → posts created → fetch engagement → engagement recorded → summary updated
  - **Task execution**: Enqueue task → task runs → analytics updated
  - **Dashboard display**: Posts exist → dashboard shows them → detail view works
- Use pytest fixtures to set up test data
- Mock external API calls
- All tests pass

**Files to create:**
- `analytics_pixelfed/tests/test_integration.py`

**Test example:**
```python
import pytest
from unittest.mock import patch, Mock
from analytics_pixelfed.services import PixelfedAnalyticsFetcher
from analytics_pixelfed.models import PixelfedPost, PixelfedLike

@pytest.mark.django_db
@patch('analytics_pixelfed.pixelfed_client.PixelfedAPIClient')
def test_full_analytics_sync_flow(mock_client_class, pixelfed_account):
    # Mock API responses
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    mock_client.get_account_posts.return_value = [
        {
            'id': '123',
            'content': 'Test post',
            'created_at': '2024-01-01T12:00:00Z',
            'url': 'https://pixelfed.social/@user/123',
            'media_attachments': [{'url': 'https://example.com/img.jpg', 'type': 'image'}]
        }
    ]

    mock_client.get_post_favourited_by.return_value = [
        {'id': 'user1', 'username': 'user1', 'display_name': 'User One'}
    ]

    mock_client.get_post_context.return_value = []
    mock_client.get_post_reblogged_by.return_value = []

    # Run sync
    fetcher = PixelfedAnalyticsFetcher(pixelfed_account)
    stats = fetcher.sync_account_posts(limit=1)

    # Verify post created
    assert stats['posts_created'] >= 1
    post = PixelfedPost.objects.get(pixelfed_post_id='123')
    assert post.caption == 'Test post'

    # Fetch engagement
    engagement_stats = fetcher.fetch_post_engagement(post)

    # Verify like created
    assert engagement_stats['new_likes'] == 1
    assert PixelfedLike.objects.filter(post=post).count() == 1

    # Verify summary updated
    assert post.engagement_summary.total_likes == 1
```

---

## Phase 12: Documentation and Deployment

### US-12.1: Update CLAUDE.md Documentation
**As a** developer
**I want to** update project documentation
**So that** future developers understand the analytics system

**Acceptance Criteria:**
- Update `CLAUDE.md` with:
  - New analytics architecture overview (separate apps per platform)
  - Explanation of platform-independent design
  - List of analytics_pixelfed models and their purpose
  - How to manually trigger analytics: commands and endpoints
  - How django-tasks works for scheduling
  - How to add new platforms (future: Instagram, Mastodon)
  - API client usage and rate limiting
  - Cross-platform dashboard features
- Remove references to old analytics implementation
- Add section on Django 6.0.1 upgrade notes
- Document testing strategy

**Files to modify:**
- `CLAUDE.md`

**New sections to add:**
```markdown
## Analytics Architecture (Django 6.0.1 + django-tasks)

PostFlow uses a **platform-independent analytics system** with separate Django apps per social platform:

- `analytics_pixelfed/` - Pixelfed analytics (media posts only)
- `analytics_instagram/` - Instagram analytics (future)
- `analytics_mastodon/` - Mastodon analytics (future)
- `analytics_core/` - Unified dashboard and cross-platform features

### Key Design Principles

1. **Platform Independence**: Analytics fetch ALL posts with media from connected accounts, not just posts created via PostFlow
2. **Granular Tracking**: Individual likes, comments, shares with timestamps and usernames
3. **Automated Updates**: django-tasks runs hourly engagement fetch (every hour at :00)
4. **Cross-Platform Insights**: Unified dashboard compares performance across platforms

### Analytics Models (analytics_pixelfed)

- **PixelfedPost**: Post metadata (caption, media_url, posted_at, etc.)
- **PixelfedLike**: Individual likes with username and timestamp
- **PixelfedComment**: Comments with content and threading (in_reply_to_id)
- **PixelfedShare**: Shares/boosts with username and timestamp
- **PixelfedEngagementSummary**: Cached counts for fast queries

### Manual Analytics Commands

```bash
# Sync posts from Pixelfed accounts
uv run manage.py sync_pixelfed_posts --all --max-posts 100

# Fetch engagement for recent posts
uv run manage.py fetch_pixelfed_engagement --all --hours 24

# Schedule hourly task (runs automatically on startup)
uv run manage.py schedule_pixelfed_analytics
```

### Adding New Platforms

To add Instagram or Mastodon analytics:

1. Create new app: `analytics_instagram/` or `analytics_mastodon/`
2. Create models: InstagramPost, InstagramLike, etc.
3. Implement API client: `instagram_client.py`
4. Create fetcher service: `services.py`
5. Add to unified dashboard: `analytics_core/views.py`

See `analytics_pixelfed/` as reference implementation.
```

---

### US-12.2: Create Deployment Migration Guide
**As a** developer
**I want to** document the production deployment process
**So that** deployment is safe and repeatable

**Acceptance Criteria:**
- Create `docs/analytics-migration.md`
- Document step-by-step deployment process:
  1. Pre-deployment checklist
  2. Django 6.0.1 upgrade verification
  3. Run migrations
  4. Initial analytics sync
  5. Verify task scheduling
  6. Monitor task execution
  7. Rollback procedure if needed
- Include SQL queries to verify data
- Note: Old analytics data will be deleted (new architecture)
- Add monitoring checklist

**Files to create:**
- `docs/analytics-migration.md`

**Document outline:**
```markdown
# Analytics System Migration Guide

## Pre-Deployment

- [ ] Backup production database
- [ ] Verify Django 6.0.1 is stable
- [ ] Test migrations on staging database
- [ ] Review GitHub Actions workflow
- [ ] Notify users of brief downtime

## Deployment Steps

### 1. Deploy Code
```bash
git push origin main  # Triggers GitHub Actions
```

### 2. Verify Django Upgrade
```bash
ssh ubuntu@server
cd /home/ubuntu/postflow
docker exec postflow_django python -c "import django; print(django.VERSION)"
# Should show (6, 0, 1, 'final', 0)
```

### 3. Run Migrations
```bash
docker exec postflow_django python manage.py migrate
# Check output for analytics_pixelfed migrations
```

### 4. Initial Analytics Sync
```bash
# Sync last 90 days of posts
docker exec postflow_django python manage.py sync_pixelfed_posts --all --max-posts 200

# Fetch engagement
docker exec postflow_django python manage.py fetch_pixelfed_engagement --all --hours 720
```

### 5. Verify Task Scheduling
```bash
docker exec postflow_django python manage.py shell
>>> from django_tasks import tasks
>>> # Check scheduled tasks
```

### 6. Monitor
- Check `/analytics/` endpoint works
- Verify posts appear in dashboard
- Monitor logs for hourly task execution
- Check for errors in `docker-compose logs django`

## Rollback Procedure

If critical issues occur:

1. Revert code: `git revert <commit> && git push`
2. Restore database from backup
3. Restart containers: `docker-compose restart`

## Verification Queries

```sql
-- Check posts synced
SELECT COUNT(*) FROM analytics_pixelfed_post;

-- Check engagement
SELECT COUNT(*) FROM analytics_pixelfed_like;
SELECT COUNT(*) FROM analytics_pixelfed_comment;

-- Check summaries calculated
SELECT COUNT(*) FROM analytics_pixelfed_engagementsummary;
```
```

---

### US-12.3: Update GitHub Actions Workflow
**As a** developer
**I want to** ensure CI/CD works with new analytics
**So that** deployments are automated

**Acceptance Criteria:**
- Review `.github/workflows/deploy.yml`
- Verify Django 6.0.1 upgrade doesn't break deployment
- Ensure migrations run on deployment
- Add step to schedule analytics tasks (if needed)
- Test deployment on staging (if available)
- Verify scheduler starts in production

**Files to check:**
- `.github/workflows/deploy.yml`

**Potential additions:**
```yaml
# In deploy job
- name: 📊 Schedule Analytics Tasks
  run: |
    ssh ubuntu@${{ secrets.EC2_HOST }} << 'EOF'
    cd /home/ubuntu/postflow
    docker exec postflow_django python manage.py schedule_pixelfed_analytics
    EOF
```

**Validation:**
- Deployment succeeds
- Migrations run automatically
- Analytics dashboard accessible
- Hourly tasks execute

---

## Phase 13: Production Rollout and Monitoring

### US-13.1: Initial Production Analytics Sync
**As a** product owner
**I want to** populate analytics for existing Pixelfed accounts
**So that** users see data immediately after deployment

**Acceptance Criteria:**
- After deployment, SSH into production server
- Run: `python manage.py sync_pixelfed_posts --all --max-posts 200`
- Run: `python manage.py fetch_pixelfed_engagement --all --hours 720` (30 days)
- Monitor execution time and errors
- Verify data appears in dashboard
- Check for API rate limiting issues
- Document any issues encountered

**Manual steps (post-deployment):**
```bash
# SSH into server
ssh ubuntu@production-server

# Sync posts (may take 5-10 minutes)
cd /home/ubuntu/postflow
docker exec postflow_django python manage.py sync_pixelfed_posts --all --max-posts 200

# Fetch engagement (may take 20-30 minutes)
docker exec postflow_django python manage.py fetch_pixelfed_engagement --all --hours 720

# Verify
docker exec postflow_django python manage.py shell
>>> from analytics_pixelfed.models import PixelfedPost
>>> PixelfedPost.objects.count()
```

**Success criteria:**
- All connected Pixelfed accounts have posts synced
- Engagement metrics populated
- No critical errors in logs
- Dashboard displays data correctly

---

### US-13.2: Monitor Hourly Task Execution
**As a** developer
**I want to** monitor the hourly analytics task
**So that** I can ensure analytics update automatically

**Acceptance Criteria:**
- Monitor task execution for first 24 hours after deployment
- Check django_tasks logs every hour
- Verify new engagement data appears
- Monitor for task failures
- Check API rate limiting issues
- Document task execution patterns (time taken, posts processed)
- Set up alerts for task failures (optional, manual monitoring is fine initially)

**Monitoring commands:**
```bash
# View Django logs
docker-compose logs -f django | grep analytics

# Check task status via shell
docker exec postflow_django python manage.py shell
>>> from django_tasks.models import Task
>>> Task.objects.filter(name='fetch_all_pixelfed_engagement').order_by('-created_at')[:10]

# Monitor system resources
docker stats postflow_django
```

**What to look for:**
- Tasks complete successfully (no exceptions)
- Execution time < 10 minutes
- New likes/comments/shares appear
- No rate limiting errors (429 responses)
- Memory usage stable

---

### US-13.3: User Communication and Feedback
**As a** product owner
**I want to** communicate the new analytics feature to users
**So that** they know how to use it

**Acceptance Criteria:**
- Create announcement (email, in-app notification, or blog post)
- Explain new analytics features:
  - Tracks ALL Pixelfed posts (not just PostFlow posts)
  - Granular engagement data (who liked, when)
  - Hourly automatic updates
  - Cross-platform dashboard (future)
- Link to analytics dashboard
- Provide feedback channel (email, form, GitHub issues)
- Monitor user feedback for first week
- Document common questions/issues

**Announcement outline:**
```markdown
# 📊 New Analytics Feature: Pixelfed Engagement Tracking

We've launched a powerful new analytics system for your Pixelfed accounts!

## What's New

✨ **Complete Post History**: View analytics for ALL your Pixelfed posts with media, not just posts created in PostFlow

📈 **Granular Engagement**: See exactly who liked, commented, and shared your posts, with timestamps

🔄 **Automatic Updates**: Analytics refresh every hour automatically

🎨 **Beautiful Dashboard**: New analytics dashboard at /analytics/pixelfed/

## How to Use

1. Go to Analytics → Pixelfed
2. View your posts and engagement metrics
3. Click any post to see detailed engagement timeline
4. Use filters to find top-performing content

## Coming Soon

- Instagram analytics
- Mastodon analytics
- Cross-platform performance comparison
- Insights and recommendations

## Feedback

We'd love to hear your thoughts! Email feedback@postflow.photo
```

---

## Success Criteria

The refactor is complete and successful when:

✅ **Phase 1-2: Infrastructure**
- Old analytics completely removed
- Django 6.0.1 installed and stable
- django-tasks configured and working

✅ **Phase 3-5: Pixelfed Analytics**
- analytics_pixelfed app created with all models
- Pixelfed API client fetches posts, likes, comments, shares
- Service layer orchestrates fetching
- Management commands work for manual operations

✅ **Phase 6-7: Automation**
- Background task runs hourly
- Task scheduling works automatically
- Tasks complete successfully without errors

✅ **Phase 8-9: Dashboards**
- Pixelfed dashboard displays posts and engagement
- Post detail view shows granular engagement
- Unified dashboard shows all platforms (currently just Pixelfed)
- Platform comparison view works

✅ **Phase 10: Visualization**
- Charts display engagement data
- Engagement timeline shows post performance

✅ **Phase 11: Testing**
- All tests pass (>90% coverage)
- Models tested
- Views tested
- Services tested
- Integration tests pass

✅ **Phase 12-13: Production**
- Documentation updated
- Successfully deployed to production
- Initial analytics sync complete
- Hourly tasks executing successfully
- Users can access and use analytics

---

## Future Enhancements (Not in this refactor)

**Platform Expansion:**
- Instagram granular analytics (separate app: analytics_instagram)
- Mastodon granular analytics (separate app: analytics_mastodon)

**Advanced Features:**
- Export analytics to CSV/PDF
- Analytics notifications ("Your post reached 100 likes!")
- Best time to post recommendations
- Hashtag performance analysis
- Follower growth tracking
- Content type analysis (photo vs carousel)
- Sentiment analysis on comments
- AI-powered content recommendations

**Performance:**
- Redis caching for dashboard queries
- Database read replicas
- Analytics data archiving (> 1 year old)

**Enterprise Features:**
- Team analytics (multi-user accounts)
- White-label reports for clients
- API access to analytics data

---

## Implementation Notes

### For AI Agents

**Clear Task Boundaries:**
- Each user story is a complete, testable unit
- Dependencies are explicit (e.g., US-4.2 requires US-4.1)
- Acceptance criteria are specific and measurable
- File paths are provided for every change

**Technical Specifications:**
- API endpoints documented
- Model fields with types specified
- Method signatures provided
- Error handling strategies defined
- Rate limiting: 1-2 seconds between requests
- Pagination: 40-80 items per page
- Timeout: 30 seconds for API calls
- Max retries: 3 with exponential backoff

**Testing Requirements:**
- Target: >90% code coverage
- Use pytest, not Django TestCase
- Mock external API calls with responses library
- Use fixtures for test data
- Test error cases, not just happy path

### For Developers

**Development Workflow:**
1. Complete Phase 1 entirely before starting Phase 2
2. Run tests after each user story
3. Commit after each completed user story
4. Use feature branches if working on team
5. Manual testing in browser after view/template changes

**Common Gotchas:**
- Pixelfed API doesn't provide like timestamps (use fetch time)
- Media URLs may need signed URLs if using S3
- Some Pixelfed instances have different API versions
- Rate limiting is conservative - can adjust if needed
- Django 6.0.1 may have breaking changes - review release notes

**Performance Considerations:**
- Use select_related() and prefetch_related() in queries
- Engagement summary caching reduces query load
- Pagination required for large engagement lists
- Consider database indexes on frequently queried fields

---

## Appendix: API Endpoints Reference

### Pixelfed API Endpoints Used

| Endpoint | Method | Purpose | Pagination |
|----------|--------|---------|------------|
| `/api/v1/accounts/{id}/statuses` | GET | Fetch account posts | Yes (max_id) |
| `/api/v1/statuses/{id}/favourited_by` | GET | Who liked post | Yes (max_id) |
| `/api/v1/statuses/{id}/reblogged_by` | GET | Who shared post | Yes (max_id) |
| `/api/v1/statuses/{id}/context` | GET | Comments/replies | No |

**Authentication:** Bearer token in Authorization header

**Rate Limiting:** Conservative (1-2 seconds between requests)

**Response Format:** JSON

**Error Handling:**
- 404: Post not found or deleted
- 401: Invalid access token
- 429: Rate limited (retry after delay)
- 500: Server error (retry with backoff)

---

**Total User Stories:** 62
**Estimated Effort:** 5-6 weeks for full implementation
**Priority:** High - Core feature for social media management platform
**Django Version:** 6.0.1
**Python Version:** >=3.13
**Target Users:** 100s of active users
**Data Retention:** Indefinite (all engagement data stored)
