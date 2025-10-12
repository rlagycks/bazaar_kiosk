from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0015_remove_menu_categories"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    CREATE INDEX IF NOT EXISTS orders_menu_is_acti_25e629_idx
                    ON orders_menuitem (is_active, sort_index, name);
                    """,
                    reverse_sql="""
                    DROP INDEX IF EXISTS orders_menu_is_acti_25e629_idx;
                    """,
                ),
            ],
            state_operations=[
                migrations.AddIndex(
                    model_name="menuitem",
                    index=models.Index(
                        fields=["is_active", "sort_index", "name"],
                        name="orders_menu_is_acti_25e629_idx",
                    ),
                )
            ],
        ),
    ]
