from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class CustomUser(AbstractUser):
    username = None  # Remove the username field
    email = models.EmailField(unique=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Tag(models.Model):
    name = models.CharField(max_length=255, unique=True, db_index=True, help_text="Name of the hashtag (e.g., #example)")

    def __str__(self):
        return self.name or "Unnamed Tag"


class TagGroup(models.Model):
    name = models.CharField(max_length=255, db_index=True, help_text="Name of the tag group")
    tags = models.ManyToManyField(Tag, related_name="tag_groups", blank=True, help_text="Tags associated with this group")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tag_groups", help_text="User who owns this tag group")

    class Meta:
        unique_together = ("name", "user")

    def __str__(self):
        return self.name or "Unnamed Tag Group"
