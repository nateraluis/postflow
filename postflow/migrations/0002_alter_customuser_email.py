# Generated by Django 5.1.3 on 2025-01-02 19:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('postflow', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='email',
            field=models.EmailField(max_length=254, unique=True),
        ),
    ]
