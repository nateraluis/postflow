# Generated migration for PostImage model and making image field optional

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0020_add_mastodon_native_accounts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduledpost',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='scheduled_posts/'),
        ),
        migrations.CreateModel(
            name='PostImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(help_text='Image file for this post', upload_to='scheduled_posts/')),
                ('order', models.PositiveIntegerField(default=0, help_text='Order of this image in the post (0-indexed)')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('scheduled_post', models.ForeignKey(help_text='The scheduled post this image belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='images', to='postflow.scheduledpost')),
            ],
            options={
                'verbose_name': 'Post Image',
                'verbose_name_plural': 'Post Images',
                'ordering': ['order'],
            },
        ),
    ]
