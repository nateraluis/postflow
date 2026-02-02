#!/usr/bin/env python
"""
Test script to call Instagram API and show raw response data.
Run with: uv run python test_instagram_api.py
"""
import os
import sys
import django
import json
from pprint import pprint

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from instagram.models import InstagramBusinessAccount
from analytics_instagram.instagram_client import InstagramAPIClient
from analytics_instagram.models import InstagramPost


def test_instagram_api():
    """Test Instagram API and show raw response."""

    # Get the first Instagram account
    account = InstagramBusinessAccount.objects.first()

    if not account:
        print("❌ No Instagram Business Account found in database")
        print("Please connect an Instagram account first")
        return

    print(f"✅ Found Instagram account: @{account.username}")
    print(f"   Instagram ID: {account.instagram_id}")
    print(f"   Access Token: {account.access_token[:20]}...")
    print()

    # Initialize API client
    client = InstagramAPIClient(access_token=account.access_token)

    # 1. Test get_user_media (list of posts)
    print("=" * 80)
    print("1. TESTING get_user_media (List of posts)")
    print("=" * 80)
    try:
        media_list = client.get_user_media(account.instagram_id, limit=3)
        print(f"✅ Successfully fetched {len(media_list)} posts")
        print()

        for i, media in enumerate(media_list, 1):
            print(f"--- Post {i} ---")
            print(f"ID: {media.get('id')}")
            print(f"Caption: {media.get('caption', '')[:100]}...")
            print(f"Media Type: {media.get('media_type')}")
            print(f"Like Count: {media.get('like_count', 0)}")
            print(f"Comments Count: {media.get('comments_count', 0)}")
            print(f"Timestamp: {media.get('timestamp')}")
            print()

        # Show full JSON for first post
        if media_list:
            print("📋 FULL JSON RESPONSE FOR FIRST POST:")
            print(json.dumps(media_list[0], indent=2))
            print()

    except Exception as e:
        print(f"❌ Error fetching media: {e}")
        print()

    # 2. Test get_media_insights (detailed insights for a post)
    print("=" * 80)
    print("2. TESTING get_media_insights (Detailed insights for a post)")
    print("=" * 80)

    # Get a post from the database
    post = InstagramPost.objects.filter(account=account).first()

    if not post:
        print("❌ No Instagram posts found in database")
        print("Please sync posts first")
        return

    print(f"Testing with post: {post.instagram_media_id}")
    print(f"Posted at: {post.posted_at}")
    print()

    try:
        # Pass the media type from the post
        insights = client.get_media_insights(post.instagram_media_id, post.media_type)
        print("✅ Successfully fetched insights")
        print()
        print("📊 INSIGHTS DATA:")
        pprint(insights)
        print()

        # Show which metrics are available
        print("📈 AVAILABLE METRICS:")
        for metric_name, metric_value in insights.items():
            print(f"  - {metric_name}: {metric_value}")
        print()

    except Exception as e:
        print(f"❌ Error fetching insights: {e}")
        print()

    # 3. Show what's currently stored in the database
    print("=" * 80)
    print("3. DATA CURRENTLY STORED IN DATABASE")
    print("=" * 80)
    print(f"Post ID: {post.instagram_media_id}")
    print(f"Username: {post.username}")
    print(f"Caption: {post.caption[:100] if post.caption else 'N/A'}...")
    print()
    print("📊 STORED METRICS:")
    print(f"  - api_like_count: {post.api_like_count}")
    print(f"  - api_comments_count: {post.api_comments_count}")
    print(f"  - api_engagement: {post.api_engagement}")
    print(f"  - api_saved: {post.api_saved}")
    print(f"  - api_reach: {post.api_reach}")
    print(f"  - api_impressions: {post.api_impressions}")
    print(f"  - api_video_views: {post.api_video_views}")
    print()

    # 4. Check engagement summary
    if hasattr(post, 'engagement_summary') and post.engagement_summary:
        print("📈 ENGAGEMENT SUMMARY:")
        summary = post.engagement_summary
        print(f"  - total_likes: {summary.total_likes}")
        print(f"  - total_comments: {summary.total_comments}")
        print(f"  - total_saved: {summary.total_saved}")
        print(f"  - total_reach: {summary.total_reach}")
        print(f"  - total_impressions: {summary.total_impressions}")
        print(f"  - total_engagement: {summary.total_engagement}")
    else:
        print("⚠️  No engagement summary found")
    print()


if __name__ == "__main__":
    test_instagram_api()
