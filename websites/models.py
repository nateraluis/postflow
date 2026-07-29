from django.conf import settings
from django.db import models

from core.fields import EncryptedJSONField


class Website(models.Model):
    """A website connected by a user as a content source for social publishing."""

    SYNC_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("syncing", "Syncing"),
        ("ok", "Synced"),
        ("error", "Error"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="websites"
    )
    url = models.URLField(help_text="Site root URL, e.g. https://example.com")
    title = models.CharField(max_length=255, blank=True)
    detected_platform = models.CharField(
        max_length=50, blank=True, help_text="e.g. ghost, wordpress, unknown"
    )
    sync_status = models.CharField(
        max_length=20, choices=SYNC_STATUS_CHOICES, default="pending"
    )
    sync_error = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "url"], name="unique_website_per_user")
        ]

    def __str__(self):
        return self.title or self.url

    @property
    def best_source(self):
        """Active content source with the highest fidelity (lowest priority number)."""
        return self.sources.filter(is_active=True).order_by("priority").first()


class ContentSource(models.Model):
    """A way of ingesting content from a website. A website can have several;
    the lowest-priority active one is used for syncing."""

    KIND_CHOICES = [
        ("ghost_content_api", "Ghost Content API"),
        ("ghost_geo", "Ghost GEO (llms.txt / .md)"),
        ("rss", "RSS / Atom feed"),
        ("sitemap_crawl", "Sitemap crawl"),
    ]

    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="sources")
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    config = EncryptedJSONField(
        default=dict, blank=True,
        help_text="Adapter config, e.g. {'api_key': ...} or {'feed_url': ...}",
    )
    priority = models.PositiveIntegerField(
        default=100, help_text="Lower = higher fidelity, used first"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["website", "kind"], name="unique_source_kind_per_website")
        ]
        ordering = ["priority"]

    def __str__(self):
        return f"{self.website}: {self.get_kind_display()}"


class BlogPost(models.Model):
    """A content item ingested from a website; the raw material for social posts."""

    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name="posts")
    source_guid = models.CharField(
        max_length=500, help_text="Stable identifier from the source (Ghost id, RSS guid, or URL)"
    )
    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, blank=True)
    url = models.URLField(max_length=1000)
    excerpt = models.TextField(blank=True)
    markdown_body = models.TextField(blank=True)
    html_body = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_promoted_at = models.DateTimeField(
        null=True, blank=True, help_text="Last time a campaign promoted this post"
    )
    promo_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["website", "source_guid"], name="unique_post_per_website")
        ]
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    @property
    def body_for_ai(self):
        """Best available body text for AI drafting."""
        return self.markdown_body or self.html_body or self.excerpt

    @property
    def feature_image(self):
        # Iterate in Python so prefetch_related("images") is honoured
        images = list(self.images.all())
        for image in images:
            if image.is_feature:
                return image
        return images[0] if images else None


class BlogPostImage(models.Model):
    """An image belonging to an ingested post, downloaded locally (S3 in prod)
    so it can be reused as a social media asset."""

    blog_post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name="images")
    source_url = models.URLField(max_length=1000)
    image = models.ImageField(upload_to="website_assets/", blank=True)
    alt_text = models.TextField(blank=True)
    is_feature = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blog_post", "source_url"], name="unique_image_per_post")
        ]
        ordering = ["order"]

    def __str__(self):
        return f"Image for {self.blog_post}"
