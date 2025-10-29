# Generated migration - Add mastodon_native_accounts to ScheduledPost

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mastodon_native', '0001_initial'),
        ('postflow', '0019_resolve_refactoring_migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledpost',
            name='mastodon_native_accounts',
            field=models.ManyToManyField(blank=True, help_text='Native Mastodon instances', to='mastodon_native.mastodonaccount'),
        ),
    ]
