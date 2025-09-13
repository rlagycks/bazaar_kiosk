# FILE: orders/migrations/0006_menuitem_visibility_flags.py
# Generated manually for S5 — add visibility flags to MenuItem
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_menuitem_channel_menuitem_created_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="menuitem",
            name="visible_counter",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="visible_booth",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="menuitem",
            name="visible_kitchen",
            field=models.BooleanField(default=True),
        ),
    ]