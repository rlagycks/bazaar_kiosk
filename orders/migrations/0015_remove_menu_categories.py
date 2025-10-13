from django.db import migrations, models


def drop_old_category_indexes(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS orders_menu_categor_10d346_idx;")
        cursor.execute("DROP INDEX IF EXISTS orders_menu_categor_8bb576_idx;")


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0014_orderitem_service_mode"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="menuitem",
            options={"ordering": ["sort_index", "name"], "indexes": []},
        ),
        migrations.AlterUniqueTogether(
            name="menuitem",
            unique_together=set(),
        ),
        migrations.RunPython(drop_old_category_indexes, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="menuitem",
            name="category",
        ),
        migrations.DeleteModel(
            name="MenuCategory",
        ),
    ]
