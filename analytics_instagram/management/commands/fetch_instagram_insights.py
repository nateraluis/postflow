"""
Management command to fetch insights for Instagram posts.

Fetches engagement metrics (likes, comments, reach, impressions, etc.) and comments
for posts from Instagram Business accounts.
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from instagram.models import InstagramBusinessAccount
from analytics_instagram.models import InstagramPost
from analytics_instagram.fetcher import InstagramAnalyticsFetcher, InstagramAPIError

logger = logging.getLogger('postflow')
User = get_user_model()


class Command(BaseCommand):
    help = 'Fetch insights and comments for Instagram posts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Specific InstagramBusinessAccount ID to fetch insights for (optional)'
        )
        parser.add_argument(
            '--post-id',
            type=int,
            help='Specific InstagramPost ID to fetch insights for (optional)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=30,
            help='Maximum number of posts to process per account (default 30 to manage rate limits)'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Email of user whose accounts to process (optional)'
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        post_id = options.get('post_id')
        limit = options.get('limit')
        user_email = options.get('user')

        # Handle single post fetch
        if post_id:
            self._fetch_single_post(post_id)
            return

        self.stdout.write(f"Fetching insights for up to {limit} posts per account")
        self.stdout.write(self.style.WARNING("Note: Instagram rate limit is 200 calls/hour"))

        # Determine which accounts to process
        if account_id:
            # Fetch for specific account
            try:
                account = InstagramBusinessAccount.objects.get(id=account_id)
                accounts = [account]
                self.stdout.write(f"Fetching insights for account: @{account.username}")
            except InstagramBusinessAccount.DoesNotExist:
                raise CommandError(f"InstagramBusinessAccount with ID {account_id} does not exist")

        elif user_email:
            # Fetch for all accounts of specific user
            try:
                user = User.objects.get(email=user_email)
                accounts = InstagramBusinessAccount.objects.filter(user=user)
                if not accounts.exists():
                    raise CommandError(f"No Instagram Business accounts found for user {user_email}")
                self.stdout.write(f"Found {accounts.count()} accounts for user {user_email}")
            except User.DoesNotExist:
                raise CommandError(f"User with email {user_email} does not exist")

        else:
            # Fetch for all Instagram Business accounts
            accounts = InstagramBusinessAccount.objects.all()
            if not accounts.exists():
                self.stdout.write(self.style.WARNING("No Instagram Business accounts found"))
                return
            self.stdout.write(f"Found {accounts.count()} Instagram Business accounts to process")

        # Track overall statistics
        total_posts = 0
        total_insights = 0
        total_comments = 0
        total_errors = []

        # Process each account
        for account in accounts:
            self.stdout.write(f"\nProcessing account: @{account.username}")

            try:
                fetcher = InstagramAnalyticsFetcher(account)
                stats = fetcher.fetch_all_insights(limit_posts=limit)

                total_posts += stats.get('posts_processed', 0)
                total_insights += stats.get('insights_fetched', 0)
                total_comments += stats.get('comments_fetched', 0)

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Processed {stats.get('posts_processed', 0)} posts: "
                        f"{stats.get('insights_fetched', 0)} insights, "
                        f"{stats.get('comments_fetched', 0)} comments"
                    )
                )

            except InstagramAPIError as e:
                error_msg = f"API error for @{account.username}: {e}"
                logger.error(error_msg)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ {e}"))

            except Exception as e:
                error_msg = f"Unexpected error for @{account.username}: {e}"
                logger.error(error_msg, exc_info=True)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ Unexpected error: {e}"))

        # Print summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("INSIGHTS FETCH SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Accounts processed: {accounts.count()}")
        self.stdout.write(f"Posts processed: {total_posts}")
        self.stdout.write(f"Insights fetched: {total_insights}")
        self.stdout.write(f"Comments fetched: {total_comments}")

        if total_errors:
            self.stdout.write(self.style.WARNING(f"Errors encountered: {len(total_errors)}"))
            for error in total_errors[:5]:  # Show first 5 errors
                self.stdout.write(self.style.ERROR(f"  - {error}"))
            if len(total_errors) > 5:
                self.stdout.write(f"  ... and {len(total_errors) - 5} more errors")
        else:
            self.stdout.write(self.style.SUCCESS("No errors encountered"))

        self.stdout.write("="*50)

        # Log completion
        logger.info(
            f"Insights fetch completed: {accounts.count()} accounts, "
            f"{total_posts} posts, {total_insights} insights, "
            f"{total_comments} comments, {len(total_errors)} errors"
        )

    def _fetch_single_post(self, post_id: int):
        """Fetch insights for a single post."""
        self.stdout.write(f"Fetching insights for post ID {post_id}")

        try:
            post = InstagramPost.objects.select_related('account').get(id=post_id)
        except InstagramPost.DoesNotExist:
            raise CommandError(f"InstagramPost with ID {post_id} does not exist")

        self.stdout.write(f"Post: @{post.username} - {post.instagram_media_id}")

        try:
            fetcher = InstagramAnalyticsFetcher(post.account)

            # Fetch insights
            self.stdout.write("  Fetching insights...")
            insights = fetcher.fetch_post_insights(post)
            if insights:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Insights: {insights}"))
            else:
                self.stdout.write(self.style.WARNING("  ⚠ No insights available"))

            # Fetch comments
            self.stdout.write("  Fetching comments...")
            new_comments = fetcher.fetch_post_comments(post)
            self.stdout.write(self.style.SUCCESS(f"  ✓ Comments: {new_comments} new"))

            self.stdout.write(self.style.SUCCESS("\nPost insights updated successfully"))

        except InstagramAPIError as e:
            self.stdout.write(self.style.ERROR(f"API error: {e}"))
            raise CommandError(f"Failed to fetch insights: {e}")

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise CommandError(f"Unexpected error: {e}")
