# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0021_postimage_model_and_optional_image'),
    ]

    operations = [
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('improvement', 'Improvement'), ('bug', 'Bug Report'), ('other', 'Other')], help_text='Type of feedback', max_length=20)),
                ('message', models.TextField(help_text='Feedback message')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('reviewed', 'Reviewed'), ('resolved', 'Resolved')], default='pending', help_text='Current status of the feedback', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(help_text='User who submitted the feedback', on_delete=django.db.models.deletion.CASCADE, related_name='feedback_submissions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Feedback',
                'verbose_name_plural': 'Feedback',
                'ordering': ['-created_at'],
            },
        ),
    ]
