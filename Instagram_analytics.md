# Instagram Analytics Implementation Plan

## Overview

This document provides a comprehensive, step-by-step implementation plan for building an Instagram analytics module for PostFlow. The plan follows the same architecture pattern as the existing `analytics_pixelfed` and `analytics_mastodon` apps, ensuring consistency and maintainability.

## Architecture Analysis

### Existing Platform Analytics Structure

Both Pixelfed and Mastodon analytics follow this pattern:

1. **Models Layer** (`models.py`):
   - Main post model (e.g., `PixelfedPost`, `MastodonPost`)
   - Individual engagement models (e.g., `PixelfedLike`, `PixelfedComment`, `PixelfedShare`)
   - Cached engagement summary model (e.g., `PixelfedEngagementSummary`)

2. **API Client Layer** (`{platform}_client.py`):
   - Handles all API communication with retry logic
   - Error handling and rate limiting
   - Endpoint-specific methods

3. **Fetcher Service Layer** (`fetcher.py`):
   - Business logic for syncing posts
   - Fetching and processing engagement data
   - Coordinates between API client and database models

4. **Background Tasks** (`tasks.py`):
   - Django 6.0 tasks for scheduled operations
   - Periodic syncing and engagement fetching
   - Manual trigger tasks

5. **Views Layer** (`views.py`):
   - Dashboard view with sorting and filtering
   - Post detail view with engagement timeline
   - AJAX endpoints for manual sync/refresh

6. **Templates**:
   - Dashboard template
   - Post detail template
   - Reusable partials (post cards, stats, toasts)

7. **Management Commands**:
   - CLI tools for syncing posts
   - CLI tools for fetching engagement

## Instagram API Capabilities

### Available Metrics (2025)

The Instagram Graph API provides the following metrics for IG Media objects:

#### Direct Fields (No Insights Endpoint Required)
- `like_count` - Total likes on the post
- `comments_count` - Total comments on the post
- `caption` - Post caption text
- `media_type` - IMAGE, VIDEO, CAROUSEL_ALBUM
- `media_url` - URL to the media file
- `permalink` - Public URL to the post
- `timestamp` - ISO 8601 formatted creation time
- `username` - Username of the account

#### Insights Endpoint (`/{media-id}/insights`)
Available for Business and Creator accounts only:

**Engagement Metrics:**
- `engagement` - Total likes + comments on the post
- `saved` - Number of unique accounts that saved the post
- `reach` - Number of unique accounts that saw the post
- `impressions` - Total number of times the post was seen

**Video Metrics (for VIDEO and REELS):**
- `video_views` - Number of times video was viewed (Reels only as of 2025)
- `plays` - Number of times Reels started to play
- `total_interactions` - Sum of likes, comments, saves, and shares

**NOTE:** As of January 2025, several metrics were deprecated in Graph API v21+:
- `video_views` for non-Reels content
- Individual demographic breakdowns
- Some time-series metrics

### API Limitations

1. **No Individual User Data**: Unlike Mastodon/Pixelfed, Instagram API does NOT provide:
   - Who liked the post (individual accounts)
   - Who commented (only comments are accessible via separate endpoint)
   - Who saved the post (only aggregate count)
   - Timestamps for individual likes/saves

2. **Comments Access**: Comments can be fetched via `/{media-id}/comments` endpoint:
   - Returns comment text, username, timestamp
   - Includes replies (nested comments)
   - Can be paginated

3. **Rate Limiting**:
   - 200 calls per hour per user
   - Rate limit headers provided in responses

4. **Token Requirements**:
   - Requires Page Access Token with `instagram_basic`, `instagram_manage_insights` permissions
   - Token must be refreshed periodically (already handled in PostFlow)

## Implementation Plan

### Phase 1: Create Django App Structure

**File:** Create new Django app
```bash
cd /Users/luisnatera/Documents/tynstudio/postflow
python manage.py startapp analytics_instagram
```

**Files to create:**
- `analytics_instagram/__init__.py`
- `analytics_instagram/apps.py`
- `analytics_instagram/models.py`
- `analytics_instagram/admin.py`
- `analytics_instagram/urls.py`
- `analytics_instagram/views.py`
- `analytics_instagram/instagram_client.py`
- `analytics_instagram/fetcher.py`
- `analytics_instagram/tasks.py`
- `analytics_instagram/tests.py`
- `analytics_instagram/management/commands/sync_instagram_posts.py`
- `analytics_instagram/management/commands/fetch_instagram_insights.py`

**Register app in `core/settings.py`:**
```python
INSTALLED_APPS = [
    # ... existing apps ...
    'analytics_instagram',
]
```

### Phase 2: Database Models

**File:** `analytics_instagram/models.py`

#### Model 1: `InstagramPost`

Stores Instagram post metadata independently of ScheduledPost.

**Fields:**
- `scheduled_post` (ForeignKey, nullable) - Link to PostFlow scheduled post
- `instagram_media_id` (CharField, unique, indexed) - Instagram media ID
- `account` (ForeignKey to InstagramBusinessAccount) - Account that posted
- `username` (CharField) - Instagram username
- `caption` (TextField, blank) - Post caption
- `media_url` (URLField) - Media file URL
- `media_type` (CharField) - IMAGE, VIDEO, CAROUSEL_ALBUM
- `permalink` (URLField) - Public post URL
- `posted_at` (DateTimeField, indexed) - When post was published
- `last_fetched_at` (DateTimeField, auto_now) - Last analytics fetch
- `created_at` (DateTimeField, auto_now_add) - Record creation in PostFlow

**Aggregate Metrics (from API):**
- `api_like_count` (IntegerField, default=0)
- `api_comments_count` (IntegerField, default=0)
- `api_engagement` (IntegerField, default=0) - Likes + comments from API
- `api_saved` (IntegerField, default=0)
- `api_reach` (IntegerField, default=0)
- `api_impressions` (IntegerField, default=0)
- `api_video_views` (IntegerField, default=0, null=True) - For Reels

**Meta:**
- `db_table = 'analytics_instagram_post'`
- `unique_together = [('account', 'instagram_media_id')]`
- `ordering = ['-posted_at']`
- Indexes on: `posted_at`, `last_fetched_at`, `account`, `media_type`

**Methods:**
- `platform` property - Returns 'instagram'
- `refresh_engagement_summary()` - Updates cached summary
- `get_engagement_rate()` - Calculates engagement / impressions * 100

#### Model 2: `InstagramComment`

Stores comments on Instagram posts with threading support.

**Fields:**
- `post` (ForeignKey to InstagramPost, related_name='comments')
- `comment_id` (CharField, unique, indexed) - Instagram comment ID
- `username` (CharField) - Commenter username
- `text` (TextField) - Comment text
- `timestamp` (DateTimeField, indexed) - When comment was posted
- `like_count` (IntegerField, default=0) - Likes on the comment
- `parent_comment_id` (CharField, null=True, blank=True) - For nested replies
- `created_at` (DateTimeField, auto_now_add)

**Meta:**
- `db_table = 'analytics_instagram_comment'`
- `ordering = ['timestamp']` (chronological for conversation flow)
- Indexes on: `timestamp`, `username`, `parent_comment_id`

**Properties:**
- `is_reply` - Returns True if parent_comment_id is set

#### Model 3: `InstagramEngagementSummary`

Cached engagement metrics for fast dashboard queries.

**Fields:**
- `post` (OneToOneField to InstagramPost, related_name='engagement_summary')
- `total_likes` (IntegerField, default=0, indexed)
- `total_comments` (IntegerField, default=0)
- `total_saved` (IntegerField, default=0)
- `total_engagement` (IntegerField, default=0, indexed) - Likes + comments + saves
- `total_reach` (IntegerField, default=0)
- `total_impressions` (IntegerField, default=0)
- `total_video_views` (IntegerField, default=0, null=True)
- `engagement_rate` (FloatField, null=True, blank=True) - (engagement/impressions)*100
- `last_updated` (DateTimeField, auto_now)

**Meta:**
- `db_table = 'analytics_instagram_engagement_summary'`

**Methods:**
- `save()` - Auto-calculates `total_engagement` and `engagement_rate`
- `update_from_post()` - Refreshes from API metrics on related post

### Phase 3: Instagram API Client

**File:** `analytics_instagram/instagram_client.py`

Similar to `PixelfedAPIClient`, but tailored for Instagram Graph API.

#### Class: `InstagramAPIClient`

**Constructor:**
```python
def __init__(self, access_token: str):
    self.access_token = access_token
    self.base_url = "https://graph.instagram.com/v22.0"
    self.session = requests.Session()
```

**Methods:**

1. `_make_request(endpoint, params=None, method='GET')`:
   - Base request method with retry logic
   - Rate limit handling (429 responses)
   - Error parsing and logging
   - Returns JSON response

2. `get_user_media(ig_user_id: str, limit: int = 50)`:
   - Fetches media posts for an IG user
   - Endpoint: `/{ig-user-id}/media`
   - Fields: `id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count`
   - Returns list of media objects

3. `get_media_insights(media_id: str)`:
   - Fetches insights for a specific media
   - Endpoint: `/{media-id}/insights`
   - Metrics: `engagement,saved,reach,impressions,video_views`
   - Returns insights dictionary

4. `get_media_comments(media_id: str)`:
   - Fetches comments for a media post
   - Endpoint: `/{media-id}/comments`
   - Fields: `id,text,username,timestamp,like_count,replies`
   - Returns list of comment objects
   - Supports pagination

5. `get_comment_replies(comment_id: str)`:
   - Fetches replies to a specific comment
   - Endpoint: `/{comment-id}/replies`
   - Returns nested comment objects

**Error Handling:**
- Custom exception: `InstagramAPIError`
- Handle rate limiting with exponential backoff
- Log all errors with context

### Phase 4: Fetcher Service

**File:** `analytics_instagram/fetcher.py`

#### Class: `InstagramAnalyticsFetcher`

**Constructor:**
```python
def __init__(self, account: InstagramBusinessAccount):
    self.account = account
    self.client = InstagramAPIClient(access_token=account.access_token)
```

**Methods:**

1. `sync_account_posts(limit: int = 50) -> Tuple[int, int]`:
   - Fetches media from Instagram API
   - Creates/updates `InstagramPost` records
   - Links to `ScheduledPost` if `instagram_post_id` matches
   - Returns (created_count, updated_count)

2. `fetch_post_insights(post: InstagramPost) -> Dict[str, int]`:
   - Calls `get_media_insights()` for a post
   - Updates post's `api_*` fields
   - Creates/updates `InstagramEngagementSummary`
   - Returns insights dictionary

3. `fetch_post_comments(post: InstagramPost) -> int`:
   - Calls `get_media_comments()` for a post
   - Creates/updates `InstagramComment` records
   - Handles nested replies recursively
   - Returns count of new comments

4. `fetch_all_insights(limit_posts: int = None) -> Dict`:
   - Fetches insights for multiple posts
   - Processes posts from most recent
   - Aggregates statistics
   - Returns summary dictionary

**Business Logic:**
- Transaction safety for database operations
- Proper timezone handling
- Duplicate detection (using `instagram_media_id`)
- Error recovery and partial success handling

### Phase 5: Background Tasks

**File:** `analytics_instagram/tasks.py`

Uses Django 6.0 tasks framework (django-tasks).

#### Task 1: `fetch_all_instagram_insights()`

**Decorator:** `@task(queue_name='default', priority=5)`

**Schedule:** Every 6 hours (matches existing analytics tasks)

**Function:**
- Gets all `InstagramBusinessAccount` objects
- For each account:
  - Create `InstagramAnalyticsFetcher`
  - Call `fetch_all_insights(limit_posts=30)`
  - Log results
  - Sleep 5 seconds between accounts (rate limiting)
- Return aggregated statistics

#### Task 2: `sync_all_instagram_posts()`

**Decorator:** `@task(queue_name='default', priority=5)`

**Schedule:** Daily

**Function:**
- Gets all `InstagramBusinessAccount` objects
- For each account:
  - Create `InstagramAnalyticsFetcher`
  - Call `sync_account_posts(limit=50)`
  - Log results
  - Sleep 5 seconds between accounts
- Return aggregated statistics

#### Task 3: `fetch_account_insights(account_id: int, limit_posts: int = 50)`

**Decorator:** `@task(queue_name='default', priority=10)`

**Trigger:** Manual (from dashboard)

**Function:**
- Fetch specific account by ID
- Run insights fetch immediately
- Return results for UI feedback

### Phase 6: Management Commands

#### Command 1: `sync_instagram_posts`

**File:** `analytics_instagram/management/commands/sync_instagram_posts.py`

**Usage:**
```bash
python manage.py sync_instagram_posts [--account-id ID] [--limit N]
```

**Options:**
- `--account-id`: Sync specific account (optional)
- `--limit`: Max posts to sync (default 50)

**Function:**
- If account-id provided: sync that account only
- Otherwise: sync all Instagram accounts
- Display progress and results

#### Command 2: `fetch_instagram_insights`

**File:** `analytics_instagram/management/commands/fetch_instagram_insights.py`

**Usage:**
```bash
python manage.py fetch_instagram_insights [--account-id ID] [--post-id ID] [--limit N]
```

**Options:**
- `--account-id`: Fetch for specific account
- `--post-id`: Fetch for specific post
- `--limit`: Max posts to process

**Function:**
- Fetch insights and comments
- Update engagement summaries
- Display detailed results

### Phase 7: Views and URLs

**File:** `analytics_instagram/views.py`

#### View 1: `dashboard(request)`

**URL:** `/analytics/instagram/`

**Function:**
- Get user's Instagram accounts
- Query `InstagramPost` with prefetch for performance
- Support sorting: recent, likes, comments, saved, engagement, reach, impressions
- Calculate summary statistics
- Find top performing post
- Render dashboard with context

**Template:** `analytics_instagram/dashboard.html`

**HTMX Support:** Return `analytics/platform_dashboard_content.html` for HTMX requests

#### View 2: `post_detail(request, post_id)`

**URL:** `/analytics/instagram/post/<int:post_id>/`

**Function:**
- Get `InstagramPost` by ID (with user permission check)
- Get comments ordered chronologically
- Calculate engagement timeline (by day)
- Render detail view

**Template:** `analytics_instagram/post_detail.html`

#### View 3: `refresh_post(request, post_id)` [POST]

**URL:** `/analytics/instagram/post/<int:post_id>/refresh/`

**Function:**
- Fetch updated insights for specific post
- Fetch new comments
- Return HX-Redirect header to reload page

#### View 4: `sync_account(request, account_id)` [POST]

**URL:** `/analytics/instagram/account/<int:account_id>/sync/`

**Function:**
- Sync posts from Instagram account
- Return toast notification partial
- Trigger HTMX refresh event

#### View 5: `fetch_insights(request, account_id)` [POST]

**URL:** `/analytics/instagram/account/<int:account_id>/fetch-insights/`

**Function:**
- Enqueue background task to fetch insights
- Return toast notification
- User receives feedback that task started

**File:** `analytics_instagram/urls.py`

```python
from django.urls import path
from . import views

app_name = 'analytics_instagram'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('post/<int:post_id>/', views.post_detail, name='post_detail'),
    path('post/<int:post_id>/refresh/', views.refresh_post, name='refresh_post'),
    path('account/<int:account_id>/sync/', views.sync_account, name='sync_account'),
    path('account/<int:account_id>/fetch-insights/', views.fetch_insights, name='fetch_insights'),
]
```

**Register in `core/urls.py`:**
```python
path('analytics/instagram/', include('analytics_instagram.urls')),
```

### Phase 8: Templates

#### Template Structure
```
analytics_instagram/templates/analytics_instagram/
├── dashboard.html
├── post_detail.html
├── post_detail_content.html
└── partials/
    ├── post_card.html
    ├── post_list.html
    ├── stats.html
    └── toast.html
```

#### Template 1: `dashboard.html`

Extends base template, includes:
- Platform selector (Instagram tab)
- Account selector dropdown
- Summary stats cards (posts, likes, comments, saved, reach, impressions)
- Sort dropdown (recent, likes, comments, saved, engagement)
- Top performing post highlight
- Grid of post cards
- Sync/refresh buttons

**Reuses:** `analytics/platform_dashboard_content.html` for HTMX rendering

#### Template 2: `post_detail.html`

Extends base template, includes:
- Post image/carousel
- Caption and metadata
- Engagement metrics (likes, comments, saved, reach, impressions)
- Engagement rate badge
- Comments list (with nested replies)
- Engagement timeline chart (Chart.js)
- Refresh button

#### Template 3: `partials/post_card.html`

Reusable post card component with:
- Thumbnail image
- Caption preview (truncated)
- Engagement metrics
- Posted date
- Link to detail view

**Uses Hyperscript ID:** `#post-card` for inclusion in other templates

### Phase 9: Admin Interface

**File:** `analytics_instagram/admin.py`

Register models for Django admin:

```python
from django.contrib import admin
from .models import InstagramPost, InstagramComment, InstagramEngagementSummary

@admin.register(InstagramPost)
class InstagramPostAdmin(admin.ModelAdmin):
    list_display = ['instagram_media_id', 'username', 'media_type', 'posted_at', 'api_like_count', 'api_reach']
    list_filter = ['media_type', 'account', 'posted_at']
    search_fields = ['caption', 'username', 'instagram_media_id']
    readonly_fields = ['created_at', 'last_fetched_at']

@admin.register(InstagramComment)
class InstagramCommentAdmin(admin.ModelAdmin):
    list_display = ['comment_id', 'username', 'post', 'timestamp', 'like_count']
    list_filter = ['timestamp', 'post__account']
    search_fields = ['text', 'username']

@admin.register(InstagramEngagementSummary)
class InstagramEngagementSummaryAdmin(admin.ModelAdmin):
    list_display = ['post', 'total_engagement', 'total_likes', 'total_comments', 'engagement_rate']
    readonly_fields = ['last_updated']
```

### Phase 10: Integration with Main Analytics Dashboard

**File:** `analytics/views.py`

Update main analytics view to include Instagram:

```python
def analytics_overview(request):
    # Get user's accounts
    pixelfed_accounts = MastodonAccount.objects.filter(
        user=request.user, instance_url__icontains='pixelfed'
    )
    mastodon_accounts = MastodonAccount.objects.filter(
        user=request.user, instance_url__icontains='mastodon'
    ).exclude(instance_url__icontains='pixelfed')
    instagram_accounts = InstagramBusinessAccount.objects.filter(
        user=request.user
    )

    # Get post counts and engagement stats
    pixelfed_stats = get_pixelfed_stats(pixelfed_accounts)
    mastodon_stats = get_mastodon_stats(mastodon_accounts)
    instagram_stats = get_instagram_stats(instagram_accounts)

    context = {
        'platforms': {
            'pixelfed': pixelfed_stats,
            'mastodon': mastodon_stats,
            'instagram': instagram_stats,
        }
    }
    return render(request, 'analytics/overview.html', context)
```

**Update Navigation:**

Add Instagram analytics link to sidebar navigation:
```html
<a href="{% url 'analytics_instagram:dashboard' %}">
    Instagram Analytics
</a>
```

### Phase 11: Testing

**File:** `analytics_instagram/tests.py`

Write comprehensive tests using pytest:

#### Test Categories:

1. **Model Tests:**
   - Test `InstagramPost` creation and updates
   - Test `InstagramComment` with threading
   - Test `InstagramEngagementSummary` calculations
   - Test unique constraints

2. **API Client Tests:**
   - Mock Instagram API responses
   - Test successful data fetching
   - Test error handling (404, 429, 500)
   - Test rate limiting retry logic

3. **Fetcher Service Tests:**
   - Test post syncing with mocked API
   - Test insights fetching
   - Test comment fetching with nested replies
   - Test duplicate handling

4. **View Tests:**
   - Test dashboard rendering
   - Test post detail view
   - Test AJAX endpoints
   - Test permission checking

5. **Integration Tests:**
   - Test full sync workflow
   - Test scheduled task execution
   - Test management commands

**Example Test:**
```python
import pytest
from django.contrib.auth import get_user_model
from analytics_instagram.models import InstagramPost
from instagram.models import InstagramBusinessAccount

@pytest.mark.django_db
def test_instagram_post_creation():
    user = get_user_model().objects.create_user(email='test@example.com')
    account = InstagramBusinessAccount.objects.create(
        user=user,
        instagram_id='123456',
        username='testuser',
        access_token='token123'
    )

    post = InstagramPost.objects.create(
        account=account,
        instagram_media_id='999888',
        username='testuser',
        caption='Test post',
        media_url='https://example.com/image.jpg',
        media_type='IMAGE',
        permalink='https://instagram.com/p/test',
        posted_at=timezone.now(),
        api_like_count=100,
        api_comments_count=5
    )

    assert post.platform == 'instagram'
    assert InstagramPost.objects.count() == 1
```

### Phase 12: Database Migrations

After creating models, generate and run migrations:

```bash
python manage.py makemigrations analytics_instagram
python manage.py migrate analytics_instagram
```

**Check migration file** to ensure:
- Proper indexes are created
- Foreign key relationships are correct
- Default values are set appropriately

### Phase 13: Scheduler Integration

**File:** `postflow/scheduler.py`

Add Instagram analytics tasks to the scheduler:

```python
from analytics_instagram.tasks import fetch_all_instagram_insights, sync_all_instagram_posts

# In start_scheduler() function:

# Fetch Instagram insights every 6 hours (offset by 15 minutes from Pixelfed)
scheduler.add_job(
    fetch_all_instagram_insights.enqueue,
    trigger=CronTrigger(hour='0,6,12,18', minute=15),
    id='fetch_instagram_insights',
    name='Fetch Instagram engagement metrics',
    replace_existing=True,
    misfire_grace_time=600
)

# Sync Instagram posts daily at 2:00 AM
scheduler.add_job(
    sync_all_instagram_posts.enqueue,
    trigger=CronTrigger(hour=2, minute=0),
    id='sync_instagram_posts',
    name='Sync Instagram posts',
    replace_existing=True,
    misfire_grace_time=600
)
```

## Key Differences from Pixelfed/Mastodon Analytics

### 1. No Individual Engagement Users

**Pixelfed/Mastodon:**
- Track who liked (username, display_name, timestamp)
- Track who shared/reblogged (username, display_name)
- Show engagement timeline with individual actions

**Instagram:**
- Only aggregate counts available (like_count, saved count)
- Cannot show "who liked this post"
- Cannot show save timestamps
- Engagement timeline based on comments only

**Implementation Impact:**
- Skip `InstagramLike` and `InstagramSave` models
- Use API aggregate fields directly
- Engagement timeline uses post creation + comment timestamps

### 2. Insights Require Separate API Call

**Pixelfed/Mastodon:**
- Engagement metrics included in post object
- Single API call gets all data

**Instagram:**
- Base post data: `/{user-id}/media`
- Insights data: `/{media-id}/insights` (separate call)
- Must make 2 API calls per post for complete data

**Implementation Impact:**
- Fetcher service makes 2 calls per post
- Cache insights in `InstagramPost.api_*` fields
- Background task separates sync vs. insights fetch

### 3. Richer Reach/Impressions Data

**Pixelfed/Mastodon:**
- No reach/impressions metrics available

**Instagram:**
- Detailed metrics: reach, impressions, saved
- Can calculate engagement rate (engagement/impressions)
- Professional analytics features

**Implementation Impact:**
- Add reach/impressions fields to models
- Calculate and display engagement rates
- Create insights-focused dashboard views

### 4. Video-Specific Metrics

**Instagram:**
- Reels have `video_views` metric
- Regular videos deprecated as of 2025
- Track media_type to determine available metrics

**Implementation Impact:**
- Add `api_video_views` field (nullable)
- Check media_type before requesting video metrics
- Display video metrics only for Reels

### 5. Rate Limiting Differences

**Pixelfed/Mastodon:**
- Generally lenient rate limits
- Per-instance rate limiting

**Instagram:**
- 200 calls/hour per user (strict)
- Must be careful with bulk operations

**Implementation Impact:**
- Add longer sleep times between accounts (5-10s)
- Limit default post processing (e.g., 30 instead of 50)
- Implement robust rate limit handling

## Implementation Checklist

Use this checklist when implementing each phase:

### Phase 1: Setup
- [ ] Create `analytics_instagram` Django app
- [ ] Register in `INSTALLED_APPS`
- [ ] Create directory structure
- [ ] Set up `__init__.py` and `apps.py`

### Phase 2: Models
- [ ] Create `InstagramPost` model
- [ ] Create `InstagramComment` model
- [ ] Create `InstagramEngagementSummary` model
- [ ] Add model methods and properties
- [ ] Generate migrations
- [ ] Run migrations
- [ ] Test migrations in staging

### Phase 3: API Client
- [ ] Create `InstagramAPIClient` class
- [ ] Implement `_make_request()` with retry logic
- [ ] Implement `get_user_media()`
- [ ] Implement `get_media_insights()`
- [ ] Implement `get_media_comments()`
- [ ] Implement `get_comment_replies()`
- [ ] Add rate limit handling
- [ ] Add comprehensive error logging
- [ ] Test with real API (dev account)

### Phase 4: Fetcher Service
- [ ] Create `InstagramAnalyticsFetcher` class
- [ ] Implement `sync_account_posts()`
- [ ] Implement `fetch_post_insights()`
- [ ] Implement `fetch_post_comments()`
- [ ] Implement `fetch_all_insights()`
- [ ] Add transaction safety
- [ ] Test with sample data
- [ ] Test error recovery

### Phase 5: Background Tasks
- [ ] Create `fetch_all_instagram_insights()` task
- [ ] Create `sync_all_instagram_posts()` task
- [ ] Create `fetch_account_insights()` task
- [ ] Test task execution manually
- [ ] Verify logging output
- [ ] Test error handling in tasks

### Phase 6: Management Commands
- [ ] Create `sync_instagram_posts` command
- [ ] Create `fetch_instagram_insights` command
- [ ] Add command options and help text
- [ ] Test commands with various options
- [ ] Document command usage

### Phase 7: Views and URLs
- [ ] Create `dashboard()` view
- [ ] Create `post_detail()` view
- [ ] Create `refresh_post()` view
- [ ] Create `sync_account()` view
- [ ] Create `fetch_insights()` view
- [ ] Create URL patterns
- [ ] Register URLs in main `urls.py`
- [ ] Test all endpoints manually

### Phase 8: Templates
- [ ] Create base dashboard template
- [ ] Create post detail template
- [ ] Create post card partial
- [ ] Create stats partial
- [ ] Create toast partial
- [ ] Add HTMX interactions
- [ ] Test responsive design
- [ ] Test HTMX refreshes

### Phase 9: Admin Interface
- [ ] Register `InstagramPost` in admin
- [ ] Register `InstagramComment` in admin
- [ ] Register `InstagramEngagementSummary` in admin
- [ ] Customize list views
- [ ] Add filters and search
- [ ] Test admin interface

### Phase 10: Integration
- [ ] Update main analytics overview
- [ ] Add navigation links
- [ ] Update dashboard to show Instagram stats
- [ ] Test cross-platform navigation
- [ ] Verify permission checks

### Phase 11: Testing
- [ ] Write model tests
- [ ] Write API client tests (mocked)
- [ ] Write fetcher service tests
- [ ] Write view tests
- [ ] Write integration tests
- [ ] Run full test suite
- [ ] Achieve >80% code coverage

### Phase 12: Scheduler Integration
- [ ] Add tasks to scheduler
- [ ] Configure cron triggers
- [ ] Test scheduled execution
- [ ] Monitor logs for errors
- [ ] Verify tasks run on schedule

### Phase 13: Documentation and Deployment
- [ ] Update main README with Instagram analytics
- [ ] Document API limitations
- [ ] Update user documentation
- [ ] Create migration guide for existing users
- [ ] Test in staging environment
- [ ] Deploy to production
- [ ] Monitor for errors post-deployment

## Expected File Structure

After implementation, the `analytics_instagram` app will have this structure:

```
analytics_instagram/
├── __init__.py
├── apps.py
├── models.py                           # InstagramPost, InstagramComment, InstagramEngagementSummary
├── admin.py                            # Django admin registration
├── urls.py                             # URL routing
├── views.py                            # Dashboard, detail, AJAX views
├── instagram_client.py                 # Instagram Graph API client
├── fetcher.py                          # InstagramAnalyticsFetcher service
├── tasks.py                            # Django tasks for background jobs
├── tests.py                            # Pytest test suite
├── management/
│   ├── __init__.py
│   └── commands/
│       ├── __init__.py
│       ├── sync_instagram_posts.py     # CLI: Sync posts from Instagram
│       └── fetch_instagram_insights.py # CLI: Fetch insights/comments
├── migrations/
│   ├── __init__.py
│   └── 0001_initial.py                 # Initial migration
└── templates/
    └── analytics_instagram/
        ├── dashboard.html              # Main dashboard
        ├── post_detail.html            # Post detail page
        ├── post_detail_content.html    # HTMX partial
        └── partials/
            ├── post_card.html          # Post card component
            ├── post_list.html          # Post list partial
            ├── stats.html              # Stats summary partial
            └── toast.html              # Toast notification partial
```

## API Rate Limit Management Strategy

Given Instagram's strict rate limits (200 calls/hour), implement these strategies:

### 1. Batch Operations
- Process max 30 posts per account per fetch
- Add 5-second delays between accounts
- Limit concurrent account processing

### 2. Caching
- Cache insights in database (don't refetch every view)
- Use `last_fetched_at` to determine staleness
- Only refetch if > 1 hour old

### 3. Prioritization
- Fetch recent posts first (last 7 days)
- Skip very old posts (>90 days) unless manually requested
- Prioritize posts with high engagement

### 4. Smart Scheduling
- Run background tasks during off-peak hours
- Stagger tasks by 15 minutes (avoid rate limit spikes)
- Monitor rate limit headers and back off if needed

### 5. Error Recovery
- On rate limit (429): pause for duration in Retry-After header
- Log rate limit events for monitoring
- Resume gracefully after rate limit expires

## Monitoring and Maintenance

### Logging
Log these events at appropriate levels:

**INFO:**
- Successful post syncs
- Insights fetch completions
- Task start/completion
- Account processing summaries

**WARNING:**
- Rate limit approaches (when near 200 calls/hour)
- API deprecation notices
- Partial failures (some posts failed)

**ERROR:**
- API authentication failures
- Persistent API errors
- Database integrity issues
- Task failures

### Metrics to Track
- Posts synced per day
- Insights fetched per day
- API errors by type
- Rate limit hits
- Average engagement rates
- Top performing posts

### Maintenance Tasks
- Monthly: Review API version for deprecations
- Weekly: Check error logs
- Daily: Monitor scheduled task execution
- As needed: Refresh test access tokens

## Security Considerations

### 1. Access Token Storage
- Tokens stored encrypted in database (existing `InstagramBusinessAccount` model)
- Never log tokens in plain text
- Refresh tokens before expiration (already handled)

### 2. User Permissions
- Users can only view their own analytics
- Check `account.user == request.user` in all views
- Use Django's `@login_required` decorator

### 3. Data Privacy
- Do not store PII from comments beyond username
- Respect Instagram's data retention policies
- Allow users to delete synced analytics data

### 4. API Key Management
- Store Facebook App credentials in environment variables
- Never commit credentials to git
- Use different credentials for dev/staging/production

## Future Enhancements

### Phase 14+ (Optional Features)

1. **Story Analytics** (if API access available):
   - Track Instagram Story views
   - Story engagement metrics
   - Story retention rates

2. **Hashtag Performance**:
   - Analyze which hashtags drive engagement
   - Suggest optimal hashtag groups
   - Track hashtag trends

3. **Best Time to Post**:
   - Analyze engagement by hour/day
   - Recommend optimal posting times
   - Visualize engagement patterns

4. **Competitor Analysis** (if API permits):
   - Compare performance to similar accounts
   - Benchmark engagement rates
   - Track industry trends

5. **Advanced Reporting**:
   - Export analytics to CSV/PDF
   - Custom date range reports
   - Email digest of top posts

6. **AI-Powered Insights**:
   - Caption analysis (what drives engagement?)
   - Image analysis (colors, composition)
   - Predictive engagement scoring

## Conclusion

This implementation plan provides a comprehensive, step-by-step guide to building Instagram analytics for PostFlow. By following the proven architecture patterns from Pixelfed and Mastodon analytics while adapting to Instagram's unique API capabilities and limitations, you'll create a robust, maintainable analytics module.

Key success factors:
- Follow existing patterns for consistency
- Handle Instagram API limitations gracefully
- Implement comprehensive error handling
- Test thoroughly at each phase
- Monitor rate limits carefully
- Document all deviations and decisions

The plan is designed to be implementable by Claude Code or another developer with clear instructions at every step. Each phase can be tackled independently, with tests and validation before moving to the next phase.
