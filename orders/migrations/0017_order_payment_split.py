from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0016_menuitem_index_if_missing"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="received_cash_amount",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="received_ticket_amount",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("CASH", "현금"),
                    ("TICKET", "티켓"),
                    ("CASH_TICKET", "현금+티켓"),
                ],
                default="CASH",
                max_length=12,
            ),
        ),
    ]
