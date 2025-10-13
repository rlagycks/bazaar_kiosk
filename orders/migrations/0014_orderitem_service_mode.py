from django.db import migrations, models


def copy_order_type_to_service_mode(apps, schema_editor):
    OrderItem = apps.get_model("orders", "OrderItem")
    for item in OrderItem.objects.all().select_related("order"):
        mode = (item.order.order_type or "DINE_IN").upper()
        if mode not in {"DINE_IN", "TAKEOUT"}:
            mode = "DINE_IN"
        item.service_mode = mode
        item.save(update_fields=["service_mode"])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0013_orderitem_prepared_qty_and_cancel_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="service_mode",
            field=models.CharField(
                choices=[("DINE_IN", "매장"), ("TAKEOUT", "포장"), ("BOOTH", "부스(1층)")],
                default="DINE_IN",
                max_length=10,
            ),
        ),
        migrations.RunPython(copy_order_type_to_service_mode, migrations.RunPython.noop),
    ]
