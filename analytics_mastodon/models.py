"""
Mastodon Analytics Models

Platform-independent analytics models for tracking Mastodon posts and engagement.
Fetches ALL posts with media from connected Mastodon accounts, not just posts
created via PostFlow.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from postflow.models import ScheduledPost
from mastodon_native.models import MastodonAccount


class MastodonPost(models.Model):
    """
    Stores Mastodon post metadata independently of ScheduledPost.

    Tracks ALL posts with media from connected Mastodon accounts,
    not just posts created through PostFlow.
    """

    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('gifv', 'GIF Video'),
        ('audio', 'Audio'),
        ('unknown', 'Unknown'),
    ]

    # Optional link to PostFlow scheduled post (null if fetched externally)
    scheduled_post = models.ForeignKey(
        ScheduledPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mastodon_analytics',
        help_text="Linked ScheduledPost if this was created via PostFlow"
    )

    # Mastodon post identification
    mastodon_post_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique Mastodon post ID"
    )

    account = models.ForeignKey(
        MastodonAccount,
        on_delete=models.CASCADE,
        related_name='mastodon_analytics_posts',
        help_text="The Mastodon account that posted this"
    )

    instance_url = models.URLField(
        max_length=255,
        help_text="Mastodon instance URL (e.g., https://mastodon.social)"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of the poster (without @)"
    )

    # Post content
    content = models.TextField(
        blank=True,
        help_text="Post content/text"
    )

    media_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="Primary image, video, or audio URL"
    )

    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        default='image',
        help_text="Type of media in the post"
    )

    post_url = models.URLField(
        max_length=500,
        help_text="Full URL to the post on Mastodon"
    )

    # Timestamps
    posted_at = models.DateTimeField(
        db_index=True,
        help_text="When the post was published on Mastodon"
    )

    edited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the post was last edited (if edited)"
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

    # Post metadata
    visibility = models.CharField(
        max_length=20,
        default='public',
        help_text="Post visibility: public, unlisted, private, or direct"
    )

    language = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="ISO 639-1 language code"
    )

    sensitive = models.BooleanField(
        default=False,
        help_text="Whether content has a content warning"
    )

    spoiler_text = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Content warning text"
    )

    # Threading (if this post is a reply)
    in_reply_to_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Parent post ID if this is a reply"
    )

    in_reply_to_account_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Parent post author account ID"
    )

    # Aggregate metrics from API (for comparison with our detailed tracking)
    api_replies_count = models.IntegerField(
        default=0,
        help_text="Reply count from API Status object"
    )

    api_reblogs_count = models.IntegerField(
        default=0,
        help_text="Reblog/boost count from API Status object"
    )

    api_favourites_count = models.IntegerField(
        default=0,
        help_text="Favourite/like count from API Status object"
    )

    class Meta:
        db_table = 'analytics_mastodon_post'
        unique_together = [('instance_url', 'mastodon_post_id')]
        indexes = [
            models.Index(fields=['posted_at']),
            models.Index(fields=['last_fetched_at']),
            models.Index(fields=['account', 'posted_at']),
            models.Index(fields=['visibility']),
            models.Index(fields=['in_reply_to_id']),
        ]
        ordering = ['-posted_at']
        verbose_name = 'Mastodon Post'
        verbose_name_plural = 'Mastodon Posts'

    def __str__(self):
        return f"@{self.username} - {self.mastodon_post_id}"

    @property
    def platform(self):
        """Returns platform identifier"""
        return 'mastodon'

    @property
    def has_media(self):
        """Returns True if post has media"""
        return bool(self.media_url)

    @property
    def is_reply(self):
        """Returns True if this post is a reply to another post"""
        return bool(self.in_reply_to_id)

    @property
    def is_edited(self):
        """Returns True if this post has been edited"""
        return bool(self.edited_at)

    @property
    def content_text(self):
        """Returns content with HTML tags stripped"""
        return strip_tags(self.content) if self.content else ''

    @cached_property
    def favourites_count(self):
        """Returns total number of favourites"""
        return self.favourites.count()

    @cached_property
    def replies_count(self):
        """Returns total number of replies"""
        return self.replies.count()

    @cached_property
    def reblogs_count(self):
        """Returns total number of reblogs"""
        return self.reblogs.count()

    def refresh_engagement_summary(self):
        """
        Updates engagement summary from current favourite/reply/reblog counts.

        Returns:
            MastodonEngagementSummary: Updated summary object
        """
        summary, created = MastodonEngagementSummary.objects.get_or_create(post=self)
        summary.update_from_post()
        return summary

    def get_recent_engagement(self, hours=24):
        """
        Returns engagement counts from last N hours.

        Args:
            hours (int): Number of hours to look back

        Returns:
            dict: Counts of favourites, replies, reblogs in time window
        """
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=hours)

        return {
            'favourites': self.favourites.filter(favourited_at__gte=cutoff).count(),
            'replies': self.replies.filter(replied_at__gte=cutoff).count(),
            'reblogs': self.reblogs.filter(reblogged_at__gte=cutoff).count(),
        }

    def get_top_favouriters(self, limit=10):
        """
        Returns users who favourited most posts from this account.

        Args:
            limit (int): Maximum number of favouriters to return

        Returns:
            QuerySet: MastodonFavourite objects with most frequent favouriters
        """
        from django.db.models import Count

        return self.favourites.values('username', 'display_name').annotate(
            favourite_count=Count('id')
        ).order_by('-favourite_count')[:limit]


class MastodonFavourite(models.Model):
    """
    Individual favourite on a Mastodon post.

    Tracks who favourited the post and when, enabling engagement timeline analysis.
    """

    post = models.ForeignKey(
        MastodonPost,
        on_delete=models.CASCADE,
        related_name='favourites',
        help_text="The post that was favourited"
    )

    account_id = models.CharField(
        max_length=100,
        help_text="Mastodon account ID of the favouriter"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of the favouriter (without @)"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of the favouriter"
    )

    favourited_at = models.DateTimeField(
        db_index=True,
        help_text="When the favourite occurred (estimated as first discovered time)"
    )

    first_seen_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
        help_text="When we first discovered this favourite (for timeline estimation)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_mastodon_favourite'
        unique_together = [('post', 'account_id')]
        indexes = [
            models.Index(fields=['favourited_at']),
            models.Index(fields=['first_seen_at']),
            models.Index(fields=['username']),
        ]
        ordering = ['-favourited_at']
        verbose_name = 'Mastodon Favourite'
        verbose_name_plural = 'Mastodon Favourites'

    def __str__(self):
        return f"{self.username} favourited {self.post.mastodon_post_id}"


class MastodonReply(models.Model):
    """
    Reply on a Mastodon post.

    Supports threading via in_reply_to_id for conversation tracking.
    """

    post = models.ForeignKey(
        MastodonPost,
        on_delete=models.CASCADE,
        related_name='replies',
        help_text="The post being replied to"
    )

    reply_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique Mastodon reply ID"
    )

    account_id = models.CharField(
        max_length=100,
        help_text="Mastodon account ID of replier"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of replier (without @)"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of replier"
    )

    content = models.TextField(
        help_text="Reply text content"
    )

    in_reply_to_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="ID of parent reply (for threading)"
    )

    replied_at = models.DateTimeField(
        db_index=True,
        help_text="When the reply was posted"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_mastodon_reply'
        indexes = [
            models.Index(fields=['replied_at']),
            models.Index(fields=['username']),
            models.Index(fields=['in_reply_to_id']),
        ]
        ordering = ['replied_at']  # Oldest first for conversation flow
        verbose_name = 'Mastodon Reply'
        verbose_name_plural = 'Mastodon Replies'

    def __str__(self):
        return f"{self.username} replied to {self.post.mastodon_post_id}"

    @property
    def is_nested_reply(self):
        """Returns True if this reply is a reply to another reply"""
        return bool(self.in_reply_to_id)

    @property
    def content_text(self):
        """Returns reply content with HTML tags stripped"""
        return strip_tags(self.content) if self.content else ''


class MastodonReblog(models.Model):
    """
    Reblog/boost of a Mastodon post.

    Tracks content virality and amplification.
    """

    post = models.ForeignKey(
        MastodonPost,
        on_delete=models.CASCADE,
        related_name='reblogs',
        help_text="The post that was reblogged"
    )

    account_id = models.CharField(
        max_length=100,
        help_text="Mastodon account ID of the reblogger"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of the reblogger (without @)"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of the reblogger"
    )

    reblogged_at = models.DateTimeField(
        db_index=True,
        help_text="When the reblog occurred (estimated as first discovered time)"
    )

    first_seen_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
        help_text="When we first discovered this reblog (for timeline estimation)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_mastodon_reblog'
        unique_together = [('post', 'account_id')]
        indexes = [
            models.Index(fields=['reblogged_at']),
            models.Index(fields=['first_seen_at']),
            models.Index(fields=['username']),
        ]
        ordering = ['-reblogged_at']
        verbose_name = 'Mastodon Reblog'
        verbose_name_plural = 'Mastodon Reblogs'

    def __str__(self):
        return f"{self.username} reblogged {self.post.mastodon_post_id}"


class MastodonEngagementSummary(models.Model):
    """
    Cached engagement metrics for fast dashboard queries.

    Automatically recalculates totals from related favourites/replies/reblogs.
    """

    post = models.OneToOneField(
        MastodonPost,
        on_delete=models.CASCADE,
        related_name='engagement_summary',
        help_text="The post these metrics belong to"
    )

    total_favourites = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Total number of favourites"
    )

    total_replies = models.IntegerField(
        default=0,
        help_text="Total number of replies"
    )

    total_reblogs = models.IntegerField(
        default=0,
        help_text="Total number of reblogs"
    )

    total_engagement = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Sum of favourites + replies + reblogs"
    )

    engagement_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Engagement rate percentage (future: based on impressions)"
    )

    last_updated = models.DateTimeField(
        auto_now=True,
        help_text="When these metrics were last updated"
    )

    class Meta:
        db_table = 'analytics_mastodon_engagement_summary'
        verbose_name = 'Mastodon Engagement Summary'
        verbose_name_plural = 'Mastodon Engagement Summaries'

    def __str__(self):
        return f"Summary for {self.post.mastodon_post_id}: {self.total_engagement} total"

    def save(self, *args, **kwargs):
        """Auto-calculate total_engagement on save"""
        self.total_engagement = self.total_favourites + self.total_replies + self.total_reblogs
        super().save(*args, **kwargs)

    def update_from_post(self):
        """
        Recalculates counts from related favourites/replies/reblogs.

        This is the canonical method for refreshing cached engagement metrics.
        """
        self.total_favourites = self.post.favourites.count()
        self.total_replies = self.post.replies.count()
        self.total_reblogs = self.post.reblogs.count()
        self.save()  # save() will calculate total_engagement
