import core.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pixelfed', '0003_alter_mastodonaccount_access_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='mastodonaccount',
            name='refresh_token',
            field=core.fields.EncryptedTextField(blank=True, default='', help_text='OAuth refresh token'),
        ),
        migrations.AddField(
            model_name='mastodonaccount',
            name='client_id',
            field=models.CharField(blank=True, default='', help_text='OAuth client ID used to obtain the token', max_length=255),
        ),
        migrations.AddField(
            model_name='mastodonaccount',
            name='client_secret',
            field=core.fields.EncryptedTextField(blank=True, default='', help_text='OAuth client secret used to obtain the token'),
        ),
        migrations.AddField(
            model_name='mastodonaccount',
            name='token_expires_at',
            field=models.DateTimeField(blank=True, help_text='When the access token expires', null=True),
        ),
    ]
