from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0012_alter_order_floor"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="prepared_qty",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("PREPARING", "준비중"),
                    ("READY", "완료"),
                    ("CANCELLED", "취소"),
                ],
                default="PREPARING",
                max_length=10,
            ),
        ),
    ]
