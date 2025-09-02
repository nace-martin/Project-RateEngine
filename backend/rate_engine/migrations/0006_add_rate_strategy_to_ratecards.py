from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0005_merge_20250903_0503"),
    ]

    operations = [
        migrations.AddField(
            model_name="ratecards",
            name="rate_strategy",
            field=models.CharField(max_length=32, null=True, blank=True, default="BREAKS"),
        ),
    ]

