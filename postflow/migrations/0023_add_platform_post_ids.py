# Generated manually to add platform post ID fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0022_feedback'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledpost',
            name='instagram_post_id',
            field=models.CharField(blank=True, max_length=255, null=True, help_text='Stores the actual Instagram post ID after publishing'),
        ),
        migrations.AddField(
            model_name='scheduledpost',
            name='pixelfed_post_id',
            field=models.CharField(blank=True, max_length=255, null=True, help_text='Stores Pixelfed post ID'),
        ),
    ]
