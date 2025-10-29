from django.db import migrations, models


def migrate_data(apps, schema_editor):
    """Migrate Instagram and Mastodon accounts to their new app tables"""
    from django.db import connection

    # Get old models
    OldInstagram = apps.get_model('postflow', 'InstagramBusinessAccount')
    OldMastodon = apps.get_model('postflow', 'MastodonAccount')

    # Get new models
    NewInstagram = apps.get_model('instagram', 'InstagramBusinessAccount')
    NewMastodon = apps.get_model('pixelfed', 'MastodonAccount')

    # Check if old tables exist (for existing installations)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'postflow_instagrambusinessaccount'
            )
        """)
        instagram_table_exists = cursor.fetchone()[0]

        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'postflow_mastodonaccount'
            )
        """)
        mastodon_table_exists = cursor.fetchone()[0]

    # Migrate Instagram accounts if old table exists
    if instagram_table_exists:
        for old_account in OldInstagram.objects.using(schema_editor.connection.alias).all():
            NewInstagram.objects.using(schema_editor.connection.alias).create(
                id=old_account.id,
                user=old_account.user,
                instagram_id=old_account.instagram_id,
                username=old_account.username,
                access_token=old_account.access_token,
                expires_at=old_account.expires_at,
                last_refreshed_at=old_account.last_refreshed_at,
            )

    # Migrate Mastodon accounts if old table exists
    if mastodon_table_exists:
        for old_account in OldMastodon.objects.using(schema_editor.connection.alias).all():
            NewMastodon.objects.using(schema_editor.connection.alias).create(
                id=old_account.id,
                user=old_account.user,
                instance_url=old_account.instance_url,
                access_token=old_account.access_token,
                username=old_account.username,
            )


def reverse_data(apps, schema_editor):
    """Remove migrated data from new app tables"""
    NewInstagram = apps.get_model('instagram', 'InstagramBusinessAccount')
    NewMastodon = apps.get_model('pixelfed', 'MastodonAccount')

    NewInstagram.objects.using(schema_editor.connection.alias).all().delete()
    NewMastodon.objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0017_scheduledpost_instagram_media_id'),
        ('instagram', '0001_initial'),
        ('pixelfed', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(migrate_data, reverse_data),
    ]
