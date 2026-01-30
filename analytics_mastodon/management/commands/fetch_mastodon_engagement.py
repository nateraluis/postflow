"""
Management command to fetch engagement metrics for Mastodon posts.

Fetches favourites, replies, and reblogs for MastodonPost records
and updates engagement summaries.
"""
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from mastodon_native.models import MastodonAccount
from analytics_mastodon.models import MastodonPost
from analytics_mastodon.fetcher import MastodonAnalyticsFetcher, MastodonAPIError

logger = logging.getLogger('postflow')
User = get_user_model()


class Command(BaseCommand):
    help = 'Fetch engagement metrics (favourites, replies, reblogs) for Mastodon posts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--account-id',
            type=int,
            help='Specific MastodonAccount ID to fetch engagement for (optional)'
        )
        parser.add_argument(
            '--post-id',
            type=str,
            help='Specific Mastodon post ID to fetch engagement for (optional)'
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
                post = MastodonPost.objects.get(mastodon_post_id=post_id)
                self.stdout.write(f"Fetching engagement for post {post_id}")
                self._fetch_single_post_engagement(post)
                return
            except MastodonPost.DoesNotExist:
                raise CommandError(f"MastodonPost with ID {post_id} does not exist")

        # Determine which accounts to process
        if account_id:
            # Fetch engagement for specific account
            try:
                account = MastodonAccount.objects.get(id=account_id)
                accounts = [account]
                self.stdout.write(f"Fetching engagement for account: {account}")
            except MastodonAccount.DoesNotExist:
                raise CommandError(f"Mastodon account with ID {account_id} does not exist")

        elif user_email:
            # Fetch engagement for all accounts of specific user
            try:
                user = User.objects.get(email=user_email)
                accounts = MastodonAccount.objects.filter(user=user)
                if not accounts.exists():
                    raise CommandError(f"No Mastodon accounts found for user {user_email}")
                self.stdout.write(f"Found {accounts.count()} accounts for user {user_email}")
            except User.DoesNotExist:
                raise CommandError(f"User with email {user_email} does not exist")

        else:
            # Fetch engagement for all accounts
            accounts = MastodonAccount.objects.all()
            if not accounts.exists():
                self.stdout.write(self.style.WARNING("No Mastodon accounts found"))
                return
            self.stdout.write(f"Found {accounts.count()} total Mastodon accounts")

        # Track overall statistics
        total_posts_processed = 0
        total_favourites = 0
        total_replies = 0
        total_reblogs = 0
        total_errors = []

        # Process each account
        for account in accounts:
            self.stdout.write(f"\nProcessing account: {account}")
            self.stdout.write(f"  Instance: {account.instance_url}")
            self.stdout.write(f"  Username: {account.username}")

            # Check if account has any posts
            post_count = MastodonPost.objects.filter(account=account).count()
            if post_count == 0:
                self.stdout.write(self.style.WARNING(f"  No posts found for this account"))
                continue

            self.stdout.write(f"  Found {post_count} posts")

            try:
                fetcher = MastodonAnalyticsFetcher(account)
                summary = fetcher.fetch_all_engagement(limit_posts=limit)

                total_posts_processed += summary['posts_processed']
                total_favourites += summary['total_favourites']
                total_replies += summary['total_replies']
                total_reblogs += summary['total_reblogs']

                if summary.get('errors'):
                    total_errors.extend(summary['errors'])

                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ Processed {summary['posts_processed']} posts: "
                        f"{summary['total_favourites']} favourites, "
                        f"{summary['total_replies']} replies, "
                        f"{summary['total_reblogs']} reblogs"
                    )
                )

            except MastodonAPIError as e:
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
        self.stdout.write(f"Total favourites fetched: {total_favourites}")
        self.stdout.write(f"Total replies fetched: {total_replies}")
        self.stdout.write(f"Total reblogs fetched: {total_reblogs}")
        self.stdout.write(f"Total engagement: {total_favourites + total_replies + total_reblogs}")

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
            f"{total_favourites} favourites, {total_replies} replies, "
            f"{total_reblogs} reblogs, {len(total_errors)} errors"
        )

    def _fetch_single_post_engagement(self, post):
        """
        Fetch engagement for a single specific post.

        Args:
            post: MastodonPost instance
        """
        self.stdout.write(f"\nPost details:")
        self.stdout.write(f"  Account: {post.account}")
        self.stdout.write(f"  Posted: {post.posted_at}")
        self.stdout.write(f"  Content: {post.content[:100]}..." if len(post.content) > 100 else f"  Content: {post.content}")

        try:
            fetcher = MastodonAnalyticsFetcher(post.account)
            engagement = fetcher.fetch_post_engagement(post)

            self.stdout.write("\n" + "="*50)
            self.stdout.write("ENGAGEMENT METRICS")
            self.stdout.write("="*50)
            self.stdout.write(f"Favourites: {engagement['favourites']}")
            self.stdout.write(f"Replies: {engagement['replies']}")
            self.stdout.write(f"Reblogs: {engagement['reblogs']}")

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
                self.stdout.write(f"Total Favourites: {summary.total_favourites}")
                self.stdout.write(f"Total Replies: {summary.total_replies}")
                self.stdout.write(f"Total Reblogs: {summary.total_reblogs}")
                self.stdout.write(f"Total Engagement: {summary.total_engagement}")
                self.stdout.write(f"Last Updated: {summary.last_updated}")

        except MastodonAPIError as e:
            logger.error(f"API error fetching engagement: {e}")
            self.stdout.write(self.style.ERROR(f"\n✗ API error: {e}"))

        except Exception as e:
            logger.error(f"Unexpected error fetching engagement: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"\n✗ Unexpected error: {e}"))
