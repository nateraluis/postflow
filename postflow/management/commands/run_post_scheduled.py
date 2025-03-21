from django.core.management.base import BaseCommand
from postflow.cron import post_scheduled


class Command(BaseCommand):
    help = 'Runs the post_scheduled function from postflow.cron'

    def handle(self, *args, **kwargs):
        self.stdout.write("Running post_scheduled...")
        post_scheduled()
        self.stdout.write("Done.")
