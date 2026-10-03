"""7A (D-048): the change handed back is stored with the order.

Additive only. Rows written before this have NULL and the API computes their
change the way it always did; the received-amount fields are not touched
(legacy reconciliation is 7C).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0025_account_permissions_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="change_amount",
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name="거스름돈"),
        ),
    ]
