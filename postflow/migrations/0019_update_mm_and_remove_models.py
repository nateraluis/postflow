from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0018_data_migrate_to_new_apps'),
    ]

    operations = [
        # Update M:M field references to point to new app models
        migrations.AlterField(
            model_name='scheduledpost',
            name='instagram_accounts',
            field=models.ManyToManyField(blank=True, to='instagram.instagrambusinessaccount'),
        ),
        migrations.AlterField(
            model_name='scheduledpost',
            name='mastodon_accounts',
            field=models.ManyToManyField(blank=True, to='pixelfed.mastodonaccount'),
        ),
    ]
