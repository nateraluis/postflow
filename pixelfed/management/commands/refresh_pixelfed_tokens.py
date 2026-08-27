import logging

from django.core.management.base import BaseCommand

from pixelfed.models import MastodonAccount
from pixelfed.tokens import ensure_fresh_token

logger = logging.getLogger("postflow")


class Command(BaseCommand):
    help = "Refresh Pixelfed/Mastodon-compatible access tokens that are close to expiry"

    def handle(self, *args, **options):
        ok = expired = 0
        for account in MastodonAccount.objects.all():
            if ensure_fresh_token(account):
                ok += 1
            else:
                expired += 1
        summary = f"Pixelfed token check: {ok} usable, {expired} expired (need reconnect)"
        logger.info(summary)
        self.stdout.write(summary)
