# D-051 / 4A4: personal accounts, permission sets and the audit trail.
#
# Forward only as an operational matter (the same policy as 0021): every
# device issued under the shared-account scheme is revoked here, so nobody
# keeps a session across the change, and the old application must not be
# restored on top of this schema. Schema reversal exists for test databases.
import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def revoke_every_live_device(apps, schema_editor):
    AuthDevice = apps.get_model("orders", "AuthDevice")
    AuthDevice.objects.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0024_order_uq_active_takeout_slot"),
    ]

    operations = [
        migrations.CreateModel(
            name="Account",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50, unique=True, verbose_name="이름")),
                ("can_serve", models.BooleanField(default=False, verbose_name="서빙")),
                ("can_monitor_hall", models.BooleanField(default=False, verbose_name="식당 모니터링")),
                ("can_monitor_takeout", models.BooleanField(default=False, verbose_name="포장 모니터링")),
                ("can_view_stats", models.BooleanField(default=False, verbose_name="누적·통계")),
                ("is_active", models.BooleanField(default=True, verbose_name="활성")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "계정", "verbose_name_plural": "계정", "ordering": ["name"]},
        ),
        # The shared-account columns go first: the new foreign key's database
        # column is also called account_id, so the old text column must be
        # gone before it is added. Every live device is revoked in between.
        migrations.RunPython(revoke_every_live_device, migrations.RunPython.noop),
        # Give the two columns an empty default before dropping them, so the
        # schema reversal used by test databases can re-add them next to the
        # revoked rows. Operationally the change is forward only.
        migrations.AlterField(
            model_name="authdevice", name="role",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AlterField(
            model_name="authdevice", name="account_id",
            field=models.CharField(blank=True, default="", max_length=150),
        ),
        migrations.RemoveField(model_name="authdevice", name="role"),
        migrations.RemoveField(model_name="authdevice", name="account_id"),
        migrations.AddField(
            model_name="authdevice",
            name="account",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="devices", to="orders.account",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="created_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="created_orders", to="orders.account", verbose_name="주문자",
            ),
        ),
        migrations.RenameField(model_name="orderrequest", old_name="role", new_name="actor"),
        migrations.AlterField(
            model_name="orderrequest",
            name="actor",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.CreateModel(
            name="OrderEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("CREATED", "주문 생성"), ("STATUS", "상태 변경"), ("PROGRESS", "조리 진행")], max_length=10)),
                ("from_status", models.CharField(blank=True, default="", max_length=10)),
                ("to_status", models.CharField(blank=True, default="", max_length=10)),
                ("prepared_qty", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="order_events", to="orders.account")),
                ("item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="events", to="orders.orderitem")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="events", to="orders.order")),
            ],
            options={"verbose_name": "주문 이력", "verbose_name_plural": "주문 이력", "ordering": ["created_at", "id"]},
        ),
    ]
