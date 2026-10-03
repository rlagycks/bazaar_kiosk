from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orders", "0029_revision_generation")]

    operations = [
        migrations.AddField(
            model_name="order",
            name="departed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
