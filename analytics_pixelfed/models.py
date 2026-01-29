"""
Pixelfed Analytics Models

Platform-independent analytics models for tracking Pixelfed posts and engagement.
Fetches ALL posts with media from connected Pixelfed accounts, not just posts
created via PostFlow.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.functional import cached_property
from postflow.models import ScheduledPost
from pixelfed.models import MastodonAccount


class PixelfedPost(models.Model):
    """
    Stores Pixelfed post metadata independently of ScheduledPost.

    Tracks ALL posts with media from connected Pixelfed accounts,
    not just posts created through PostFlow.
    """

    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('carousel', 'Carousel'),
    ]

    # Optional link to PostFlow scheduled post (null if fetched externally)
    scheduled_post = models.ForeignKey(
        ScheduledPost,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pixelfed_analytics',
        help_text="Linked ScheduledPost if this was created via PostFlow"
    )

    # Pixelfed post identification
    pixelfed_post_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique Pixelfed post ID"
    )

    account = models.ForeignKey(
        MastodonAccount,
        on_delete=models.CASCADE,
        related_name='analytics_posts',
        help_text="The Pixelfed account that posted this"
    )

    instance_url = models.URLField(
        max_length=255,
        help_text="Pixelfed instance URL (e.g., https://pixelfed.social)"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of the poster (without @)"
    )

    # Post content
    caption = models.TextField(
        blank=True,
        help_text="Post caption/description"
    )

    media_url = models.URLField(
        max_length=500,
        help_text="Primary image or video URL"
    )

    media_type = models.CharField(
        max_length=20,
        choices=MEDIA_TYPE_CHOICES,
        default='image',
        help_text="Type of media in the post"
    )

    post_url = models.URLField(
        max_length=500,
        help_text="Full URL to the post on Pixelfed"
    )

    # Timestamps
    posted_at = models.DateTimeField(
        db_index=True,
        help_text="When the post was published on Pixelfed"
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
        help_text="ISO 639-1 language code"
    )

    sensitive = models.BooleanField(
        default=False,
        help_text="Whether content has a content warning"
    )

    spoiler_text = models.CharField(
        max_length=500,
        blank=True,
        help_text="Content warning text"
    )

    # Threading (if this post is a reply)
    in_reply_to_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Parent post ID if this is a reply"
    )

    in_reply_to_account_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Parent post author account ID"
    )

    # Aggregate metrics from API (for comparison with our detailed tracking)
    api_replies_count = models.IntegerField(
        default=0,
        help_text="Reply count from API Status object"
    )

    api_reblogs_count = models.IntegerField(
        default=0,
        help_text="Reblog/share count from API Status object"
    )

    api_favourites_count = models.IntegerField(
        default=0,
        help_text="Favorite/like count from API Status object"
    )

    class Meta:
        db_table = 'analytics_pixelfed_post'
        unique_together = [('instance_url', 'pixelfed_post_id')]
        indexes = [
            models.Index(fields=['posted_at']),
            models.Index(fields=['last_fetched_at']),
            models.Index(fields=['account', 'posted_at']),
            models.Index(fields=['visibility']),
            models.Index(fields=['in_reply_to_id']),
        ]
        ordering = ['-posted_at']
        verbose_name = 'Pixelfed Post'
        verbose_name_plural = 'Pixelfed Posts'

    def __str__(self):
        return f"@{self.username} - {self.pixelfed_post_id}"

    @property
    def platform(self):
        """Returns platform identifier"""
        return 'pixelfed'

    @property
    def has_media(self):
        """All posts in this model have media by design"""
        return True

    @property
    def is_reply(self):
        """Returns True if this post is a reply to another post"""
        return bool(self.in_reply_to_id)

    @property
    def is_edited(self):
        """Returns True if this post has been edited"""
        return bool(self.edited_at)

    @cached_property
    def likes_count(self):
        """Returns total number of likes"""
        return self.likes.count()

    @cached_property
    def comments_count(self):
        """Returns total number of comments"""
        return self.comments.count()

    @cached_property
    def shares_count(self):
        """Returns total number of shares"""
        return self.shares.count()

    def refresh_engagement_summary(self):
        """
        Updates engagement summary from current like/comment/share counts.

        Returns:
            PixelfedEngagementSummary: Updated summary object
        """
        summary, created = PixelfedEngagementSummary.objects.get_or_create(post=self)
        summary.update_from_post()
        return summary

    def get_recent_engagement(self, hours=24):
        """
        Returns engagement counts from last N hours.

        Args:
            hours (int): Number of hours to look back

        Returns:
            dict: Counts of likes, comments, shares in time window
        """
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(hours=hours)

        return {
            'likes': self.likes.filter(liked_at__gte=cutoff).count(),
            'comments': self.comments.filter(commented_at__gte=cutoff).count(),
            'shares': self.shares.filter(shared_at__gte=cutoff).count(),
        }

    def get_top_likers(self, limit=10):
        """
        Returns users who liked most posts from this account.

        Args:
            limit (int): Maximum number of likers to return

        Returns:
            QuerySet: PixelfedLike objects with most frequent likers
        """
        from django.db.models import Count

        return self.likes.values('username', 'display_name').annotate(
            like_count=Count('id')
        ).order_by('-like_count')[:limit]


class PixelfedLike(models.Model):
    """
    Individual like/favorite on a Pixelfed post.

    Tracks who liked the post and when, enabling engagement timeline analysis.
    """

    post = models.ForeignKey(
        PixelfedPost,
        on_delete=models.CASCADE,
        related_name='likes',
        help_text="The post that was liked"
    )

    account_id = models.CharField(
        max_length=100,
        help_text="Pixelfed account ID of the liker"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of the liker (without @)"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of the liker"
    )

    liked_at = models.DateTimeField(
        db_index=True,
        help_text="When the like occurred (estimated as first discovered time)"
    )

    first_seen_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
        help_text="When we first discovered this like (for timeline estimation)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_pixelfed_like'
        unique_together = [('post', 'account_id')]
        indexes = [
            models.Index(fields=['liked_at']),
            models.Index(fields=['first_seen_at']),
            models.Index(fields=['username']),
        ]
        ordering = ['-liked_at']
        verbose_name = 'Pixelfed Like'
        verbose_name_plural = 'Pixelfed Likes'

    def __str__(self):
        return f"{self.username} liked {self.post.pixelfed_post_id}"


class PixelfedComment(models.Model):
    """
    Comment/reply on a Pixelfed post.

    Supports threading via in_reply_to_id for conversation tracking.
    """

    post = models.ForeignKey(
        PixelfedPost,
        on_delete=models.CASCADE,
        related_name='comments',
        help_text="The post being commented on"
    )

    comment_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique Pixelfed comment ID"
    )

    account_id = models.CharField(
        max_length=100,
        help_text="Pixelfed account ID of commenter"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of commenter (without @)"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of commenter"
    )

    content = models.TextField(
        help_text="Comment text content"
    )

    in_reply_to_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="ID of parent comment (for threading)"
    )

    commented_at = models.DateTimeField(
        db_index=True,
        help_text="When the comment was posted"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_pixelfed_comment'
        indexes = [
            models.Index(fields=['commented_at']),
            models.Index(fields=['username']),
            models.Index(fields=['in_reply_to_id']),
        ]
        ordering = ['commented_at']  # Oldest first for conversation flow
        verbose_name = 'Pixelfed Comment'
        verbose_name_plural = 'Pixelfed Comments'

    def __str__(self):
        return f"{self.username} commented on {self.post.pixelfed_post_id}"

    @property
    def is_reply(self):
        """Returns True if this comment is a reply to another comment"""
        return bool(self.in_reply_to_id)


class PixelfedShare(models.Model):
    """
    Share/boost/reblog of a Pixelfed post.

    Tracks content virality and amplification.
    """

    post = models.ForeignKey(
        PixelfedPost,
        on_delete=models.CASCADE,
        related_name='shares',
        help_text="The post that was shared"
    )

    account_id = models.CharField(
        max_length=100,
        help_text="Pixelfed account ID of the sharer"
    )

    username = models.CharField(
        max_length=100,
        help_text="Username of the sharer (without @)"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of the sharer"
    )

    shared_at = models.DateTimeField(
        db_index=True,
        help_text="When the share occurred (estimated as first discovered time)"
    )

    first_seen_at = models.DateTimeField(
        db_index=True,
        default=timezone.now,
        help_text="When we first discovered this share (for timeline estimation)"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created in PostFlow"
    )

    class Meta:
        db_table = 'analytics_pixelfed_share'
        unique_together = [('post', 'account_id')]
        indexes = [
            models.Index(fields=['shared_at']),
            models.Index(fields=['first_seen_at']),
            models.Index(fields=['username']),
        ]
        ordering = ['-shared_at']
        verbose_name = 'Pixelfed Share'
        verbose_name_plural = 'Pixelfed Shares'

    def __str__(self):
        return f"{self.username} shared {self.post.pixelfed_post_id}"


class PixelfedEngagementSummary(models.Model):
    """
    Cached engagement metrics for fast dashboard queries.

    Automatically recalculates totals from related likes/comments/shares.
    """

    post = models.OneToOneField(
        PixelfedPost,
        on_delete=models.CASCADE,
        related_name='engagement_summary',
        help_text="The post these metrics belong to"
    )

    total_likes = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Total number of likes"
    )

    total_comments = models.IntegerField(
        default=0,
        help_text="Total number of comments"
    )

    total_shares = models.IntegerField(
        default=0,
        help_text="Total number of shares"
    )

    total_engagement = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Sum of likes + comments + shares"
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
        db_table = 'analytics_pixelfed_engagement_summary'
        verbose_name = 'Pixelfed Engagement Summary'
        verbose_name_plural = 'Pixelfed Engagement Summaries'

    def __str__(self):
        return f"Summary for {self.post.pixelfed_post_id}: {self.total_engagement} total"

    def save(self, *args, **kwargs):
        """Auto-calculate total_engagement on save"""
        self.total_engagement = self.total_likes + self.total_comments + self.total_shares
        super().save(*args, **kwargs)

    def update_from_post(self):
        """
        Recalculates counts from related likes/comments/shares.

        This is the canonical method for refreshing cached engagement metrics.
        """
        self.total_likes = self.post.likes.count()
        self.total_comments = self.post.comments.count()
        self.total_shares = self.post.shares.count()
        self.save()  # save() will calculate total_engagement
