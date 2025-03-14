# Generated by Django 5.1.6 on 2025-02-28 10:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0011_scheduledpost_user_timezone'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledpost',
            name='mastodon_media_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='scheduledpost',
            name='mastodon_post_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='scheduledpost',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('scheduled', 'Scheduled'), ('posted', 'Posted'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
    ]
