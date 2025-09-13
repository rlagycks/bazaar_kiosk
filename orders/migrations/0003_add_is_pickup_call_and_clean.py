from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_pickupcounter_alter_table_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='is_pickup_call',
            field=models.BooleanField(default=False),
        ),
    ]