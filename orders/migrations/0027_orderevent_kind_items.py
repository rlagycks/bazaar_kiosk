"""7B (D-052): an event kind for lines changed after the order was taken.

Choices only; no SQL is generated for PostgreSQL. Existing rows are untouched.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0026_order_change_amount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("CREATED", "주문 생성"),
                    ("STATUS", "상태 변경"),
                    ("PROGRESS", "조리 진행"),
                    ("ITEMS", "품목 수정"),
                ],
                max_length=10,
            ),
        ),
    ]
