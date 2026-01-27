"""
Management command to fetch engagement metrics for Pixelfed posts.

Fetches likes, comments, and shares for PixelfedPost records
and updates engagement summaries.
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from pixelfed.models import MastodonAccount
from analytics_pixelfed.models import PixelfedPost
from analytics_pixelfed.fetcher import PixelfedAnalyticsFetcher, PixelfedAPIError

logger = logging.getLogger('postflow')
User = get_user_model()


class Command(BaseCommand):
    help = 'Fetch engagement metrics (likes, comments, shares) for Pixelfed posts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Specific MastodonAccount ID to fetch engagement for (optional)'
        )
        parser.add_argument(
            '--post-id',
            type=str,
            help='Specific Pixelfed post ID to fetch engagement for (optional)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=20,
            help='Maximum number of posts to process per account (default: 20)'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Email of user whose posts to fetch engagement for (optional)'
        )

    def handle(self, *args, **options):
        account_id = options.get('account_id')
        post_id = options.get('post_id')
        limit = options['limit']
        user_email = options.get('user')

        # Handle specific post ID
        if post_id:
            try:
                post = PixelfedPost.objects.get(pixelfed_post_id=post_id)
                self.stdout.write(f"Fetching engagement for post {post_id}")
                self._fetch_single_post_engagement(post)
                return
            except PixelfedPost.DoesNotExist:
                raise CommandError(f"PixelfedPost with ID {post_id} does not exist")

        # Determine which accounts to process
        if account_id:
            # Fetch engagement for specific account
            try:
                account = MastodonAccount.objects.get(id=account_id)
                accounts = [account]
                self.stdout.write(f"Fetching engagement for account: {account}")
            except MastodonAccount.DoesNotExist:
                raise CommandError(f"MastodonAccount with ID {account_id} does not exist")

        elif user_email:
            # Fetch engagement for all accounts of specific user
            try:
                user = User.objects.get(email=user_email)
                accounts = MastodonAccount.objects.filter(user=user)
                if not accounts.exists():
                    raise CommandError(f"No Pixelfed accounts found for user {user_email}")
                self.stdout.write(f"Found {accounts.count()} accounts for user {user_email}")
            except User.DoesNotExist:
                raise CommandError(f"User with email {user_email} does not exist")

        else:
            # Fetch engagement for all accounts
            accounts = MastodonAccount.objects.all()
            if not accounts.exists():
                self.stdout.write(self.style.WARNING("No Pixelfed accounts found"))
                return
            self.stdout.write(f"Found {accounts.count()} total Pixelfed accounts")

        # Track overall statistics
        total_posts_processed = 0
        total_likes = 0
        total_comments = 0
        total_shares = 0
        total_errors = []

        # Process each account
        for account in accounts:
            self.stdout.write(f"\nProcessing account: {account}")
            self.stdout.write(f"  Instance: {account.instance_url}")
            self.stdout.write(f"  Username: {account.username}")

            # Check if account has any posts
            post_count = PixelfedPost.objects.filter(account=account).count()
            if post_count == 0:
                self.stdout.write(self.style.WARNING(f"  No posts found for this account"))
                continue

            self.stdout.write(f"  Found {post_count} posts")

            try:
                fetcher = PixelfedAnalyticsFetcher(account)
                summary = fetcher.fetch_all_engagement(limit_posts=limit)

                total_posts_processed += summary['posts_processed']
                total_likes += summary['total_likes']
                total_comments += summary['total_comments']
                total_shares += summary['total_shares']

                if summary.get('errors'):
                    total_errors.extend(summary['errors'])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Processed {summary['posts_processed']} posts: "
                        f"{summary['total_likes']} likes, "
                        f"{summary['total_comments']} comments, "
                        f"{summary['total_shares']} shares"
                    )
                )

            except PixelfedAPIError as e:
                error_msg = f"API error for {account}: {e}"
                logger.error(error_msg)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ {e}"))

            except Exception as e:
                error_msg = f"Unexpected error for {account}: {e}"
                logger.error(error_msg, exc_info=True)
                total_errors.append(error_msg)
                self.stdout.write(self.style.ERROR(f"  ✗ Unexpected error: {e}"))

        # Print summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write("ENGAGEMENT FETCH SUMMARY")
        self.stdout.write("="*50)
        self.stdout.write(f"Accounts processed: {accounts.count()}")
        self.stdout.write(f"Posts processed: {total_posts_processed}")
        self.stdout.write(f"Total likes fetched: {total_likes}")
        self.stdout.write(f"Total comments fetched: {total_comments}")
        self.stdout.write(f"Total shares fetched: {total_shares}")
        self.stdout.write(f"Total engagement: {total_likes + total_comments + total_shares}")

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
            f"Engagement fetch completed: {total_posts_processed} posts, "
            f"{total_likes} likes, {total_comments} comments, "
            f"{total_shares} shares, {len(total_errors)} errors"
        )

    def _fetch_single_post_engagement(self, post):
        """
        Fetch engagement for a single specific post.

        Args:
            post: PixelfedPost instance
        """
        self.stdout.write(f"\nPost details:")
        self.stdout.write(f"  Account: {post.account}")
        self.stdout.write(f"  Posted: {post.posted_at}")
        self.stdout.write(f"  Caption: {post.caption[:100]}..." if len(post.caption) > 100 else f"  Caption: {post.caption}")

        try:
            fetcher = PixelfedAnalyticsFetcher(post.account)
            engagement = fetcher.fetch_post_engagement(post)

            self.stdout.write("\n" + "="*50)
            self.stdout.write("ENGAGEMENT METRICS")
            self.stdout.write("="*50)
            self.stdout.write(f"Likes: {engagement['likes']}")
            self.stdout.write(f"Comments: {engagement['comments']}")
            self.stdout.write(f"Shares: {engagement['shares']}")

            if engagement.get('errors'):
                self.stdout.write(self.style.WARNING(f"\nErrors encountered:"))
                for error in engagement['errors']:
                    self.stdout.write(self.style.ERROR(f"  - {error}"))
            else:
                self.stdout.write(self.style.SUCCESS("\n✓ Engagement fetched successfully"))

            # Show engagement summary
            if hasattr(post, 'engagement_summary'):
                summary = post.engagement_summary
                self.stdout.write("\n" + "="*50)
                self.stdout.write("UPDATED SUMMARY")
                self.stdout.write("="*50)
                self.stdout.write(f"Total Likes: {summary.total_likes}")
                self.stdout.write(f"Total Comments: {summary.total_comments}")
                self.stdout.write(f"Total Shares: {summary.total_shares}")
                self.stdout.write(f"Total Engagement: {summary.total_engagement}")
                self.stdout.write(f"Last Updated: {summary.last_updated}")

        except PixelfedAPIError as e:
            logger.error(f"API error fetching engagement: {e}")
            self.stdout.write(self.style.ERROR(f"\n✗ API error: {e}"))

        except Exception as e:
            logger.error(f"Unexpected error fetching engagement: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"\n✗ Unexpected error: {e}"))