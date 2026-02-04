"""
Instagram Analytics Models

Platform-independent analytics models for tracking Instagram posts and engagement.
Fetches ALL posts with media from connected Instagram Business accounts, not just posts
created via PostFlow.

Note: Instagram API limitations:
- No individual like/save user data (only aggregate counts)
- Comments can be fetched with threading
- Insights require separate API call
- Rate limited to 200 calls/hour per user
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from postflow.models import ScheduledPost
from instagram.models import InstagramBusinessAccount


class InstagramPost(models.Model):
    """
    Stores Instagram post metadata independently of ScheduledPost.

    Tracks ALL posts with media from connected Instagram Business accounts,
    not just posts created through PostFlow.
    """

    MEDIA_TYPE_CHOICES = [
        ('IMAGE', 'Image'),
        ('VIDEO', 'Video'),
        ('CAROUSEL_ALBUM', 'Carousel'),
    ]

    # Optional link to PostFlow scheduled post (null if fetched externally)
    scheduled_post = models.ForeignKey(
        ScheduledPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instagram_analytics',
        help_text="Linked ScheduledPost if this was created via PostFlow"
    )

    # Instagram post identification
    instagram_media_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique Instagram media ID"
    )

    account = models.ForeignKey(
        InstagramBusinessAccount,
        on_delete=models.CASCADE,
        related_name='analytics_posts',
        help_text="The Instagram Business account that posted this"
    )

    username = models.CharField(
        max_length=100,
        help_text="Instagram username (without @)"
    )

    # Post content
    caption = models.TextField(
        blank=True,
        help_text="Post caption/description"
    )

    media_url = models.URLField(
        max_length=2048,
        help_text="Primary image or video URL from Instagram API"
    )

    # Stored image file (downloaded from Instagram CDN and saved to S3)
    cached_image = models.ImageField(
        upload_to='analytics/instagram/%Y/%m/',
        null=True,
        blank=True,
        help_text="Cached copy of the media file stored in S3"
    )

    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        default='IMAGE',
        help_text="Type of media in the post"
    )

    permalink = models.URLField(
        max_length=2048,
        help_text="Public URL to the post on Instagram"
    )

    # Timestamps
    posted_at = models.DateTimeField(
        db_index=True,
        help_text="When the post was published on Instagram"
    )

    last_fetched_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        help_text="Last time analytics were fetched"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    # Aggregate metrics from API (direct fields - no insights endpoint needed)
    api_like_count = models.IntegerField(
        default=0,
        help_text="Total likes from API"
    )

    api_comments_count = models.IntegerField(
        default=0,
        help_text="Total comments count from API"
    )

    # Aggregate metrics from Insights API (requires separate call)
    api_engagement = models.IntegerField(
        default=0,
        help_text="Engagement metric from Insights API (likes + comments)"
    )

    api_saved = models.IntegerField(
        default=0,
        help_text="Number of accounts that saved the post (Insights API)"
    )

    api_reach = models.IntegerField(
        default=0,
        help_text="Number of unique accounts that saw the post (Insights API)"
    )

    api_impressions = models.IntegerField(
        default=0,
        help_text="Total number of times post was seen (Insights API)"
    )

    api_video_views = models.IntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Video views for Reels (Insights API, null for non-video)"
    )

    class Meta:
        db_table = 'analytics_instagram_post'
        unique_together = [('account', 'instagram_media_id')]
        indexes = [
            models.Index(fields=['posted_at']),
            models.Index(fields=['last_fetched_at']),
            models.Index(fields=['account', 'posted_at']),
            models.Index(fields=['media_type']),
        ]
        ordering = ['-posted_at']
        verbose_name = 'Instagram Post'
        verbose_name_plural = 'Instagram Posts'

    def __str__(self):
        return f"@{self.username} - {self.instagram_media_id}"

    @property
    def platform(self):
        """Returns platform identifier"""
        return 'instagram'

    @property
    def has_media(self):
        """All posts in this model have media by design"""
        return True

    @property
    def is_video(self):
        """Returns True if this is a video or Reel"""
        return self.media_type == 'VIDEO'

    @property
    def is_carousel(self):
        """Returns True if this is a carousel post"""
        return self.media_type == 'CAROUSEL_ALBUM'

    @property
    def caption_text(self):
        """Returns caption with HTML tags stripped"""
        return strip_tags(self.caption) if self.caption else ''

    @cached_property
    def comments_count(self):
        """Returns total number of comments tracked in our database"""
        return self.comments.count()

    def get_display_image_url(self):
        """
        Returns the URL to display for this post.
        Prefers cached_image (stored in S3) over media_url (Instagram CDN).

        In production with S3 storage, generates a fresh signed URL each time
        to prevent expired URL issues. Signed URLs are valid for 1 hour.

        Returns:
            str: URL to the image
        """
        if self.cached_image:
            # For S3 storage with signed URLs, we need to generate fresh URLs
            # The .url property may cache expired URLs, so we call storage.url() directly
            from django.conf import settings
            if not settings.DEBUG and hasattr(self.cached_image, 'storage'):
                # Generate fresh signed URL using storage backend
                # The expiry is controlled by AWS_QUERYSTRING_EXPIRE (default 3600s)
                return self.cached_image.storage.url(self.cached_image.name)
            return self.cached_image.url
        return self.media_url

    def get_engagement_rate(self):
        """
        Calculates engagement rate as (engagement / impressions) * 100.

        Returns:
            float: Engagement rate percentage, or None if no impressions
        """
        if self.api_impressions > 0:
            return (self.api_engagement / self.api_impressions) * 100
        return None

    def refresh_engagement_summary(self):
        """
        Updates engagement summary from current API metrics.

        Returns:
            InstagramEngagementSummary: Updated summary object
        """
        summary, created = InstagramEngagementSummary.objects.get_or_create(post=self)
        summary.update_from_post()
        return summary


class InstagramComment(models.Model):
    """
    Comment/reply on an Instagram post.

    Supports threading via parent_comment_id for conversation tracking.
    Note: Instagram API provides comment data, unlike likes/saves.
    """

    post = models.ForeignKey(
        InstagramPost,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="The post being commented on"
    )

    comment_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique Instagram comment ID"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of commenter (without @)"
    )

    text = models.TextField(
        help_text="Comment text content"
    )

    timestamp = models.DateTimeField(
        db_index=True,
        help_text="When the comment was posted"
    )

    like_count = models.IntegerField(
        default=0,
        help_text="Number of likes on this comment"
    )

    parent_comment_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of parent comment (for threaded replies)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_instagram_comment'
        indexes = [
            models.Index(fields=['timestamp']),
            models.Index(fields=['username']),
            models.Index(fields=['parent_comment_id']),
            models.Index(fields=['post', 'username']),  # Composite index for top engagers query
        ]
        ordering = ['timestamp']  # Oldest first for conversation flow
        verbose_name = 'Instagram Comment'
        verbose_name_plural = 'Instagram Comments'

    def __str__(self):
        return f"{self.username} commented on {self.post.instagram_media_id}"

    @property
    def is_reply(self):
        """Returns True if this comment is a reply to another comment"""
        return bool(self.parent_comment_id)

    @property
    def text_content(self):
        """Returns comment text with HTML tags stripped"""
        return strip_tags(self.text) if self.text else ''


class InstagramEngagementSummary(models.Model):
    """
    Cached engagement metrics for fast dashboard queries.

    Automatically recalculates totals from API metrics on related post.
    Note: Unlike Pixelfed, we use API aggregate counts since individual
    like/save users are not available from Instagram API.
    """

    post = models.OneToOneField(
        InstagramPost,
        on_delete=models.CASCADE,
        related_name='engagement_summary',
        help_text="The post these metrics belong to"
    )

    total_likes = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Total number of likes (from API)"
    )

    total_comments = models.IntegerField(
        default=0,
        help_text="Total number of comments (from API)"
    )

    total_saved = models.IntegerField(
        default=0,
        help_text="Total number of saves (from API)"
    )

    total_engagement = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Sum of likes + comments + saves (from API)"
    )

    total_reach = models.IntegerField(
        default=0,
        help_text="Number of unique accounts reached (from API)"
    )

    total_impressions = models.IntegerField(
        default=0,
        help_text="Total impressions (from API)"
    )

    total_video_views = models.IntegerField(
        default=0,
        null=True,
        blank=True,
        help_text="Total video views for Reels (from API)"
    )

    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Engagement rate percentage (engagement/impressions * 100)"
    )

    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="When these metrics were last updated"
    )

    class Meta:
        db_table = 'analytics_instagram_engagement_summary'
        indexes = [
            models.Index(fields=['-total_engagement']),  # For sorting by engagement (descending)
            models.Index(fields=['-total_likes']),  # For sorting by likes
            models.Index(fields=['-total_comments']),  # For sorting by comments
            models.Index(fields=['-total_saved']),  # For sorting by saves
            models.Index(fields=['-total_reach']),  # For sorting by reach
        ]
        verbose_name = 'Instagram Engagement Summary'
        verbose_name_plural = 'Instagram Engagement Summaries'

    def __str__(self):
        return f"Summary for {self.post.instagram_media_id}: {self.total_engagement} total"

    def save(self, *args, **kwargs):
        """Auto-calculate total_engagement and engagement_rate on save"""
        self.total_engagement = self.total_likes + self.total_comments + self.total_saved

        # Calculate engagement rate if we have impressions
        if self.total_impressions > 0:
            self.engagement_rate = (self.total_engagement / self.total_impressions) * 100
        else:
            self.engagement_rate = None

        super().save(*args, **kwargs)

    def update_from_post(self):
        """
        Recalculates counts from API metrics on the related post.

        This is the canonical method for refreshing cached engagement metrics.
        """
        self.total_likes = self.post.api_like_count
        self.total_comments = self.post.api_comments_count
        self.total_saved = self.post.api_saved
        self.total_reach = self.post.api_reach
        self.total_impressions = self.post.api_impressions
        self.total_video_views = self.post.api_video_views
        self.save()  # save() will calculate total_engagement and engagement_rate
