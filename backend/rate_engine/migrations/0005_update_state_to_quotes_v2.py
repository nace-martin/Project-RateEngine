from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0004_create_quotes_v2_tables"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="QuoteLines"),
                migrations.DeleteModel(name="Quotes"),
                migrations.CreateModel(
                    name="Quotes",
                    fields=[
                        ("id", models.BigAutoField(primary_key=True, serialize=False)),
                        ("status", models.CharField(default="COMPLETE", max_length=32)),
                        ("request_snapshot", models.JSONField()),
                        ("buy_total", models.DecimalField(decimal_places=2, max_digits=14)),
                        ("sell_total", models.DecimalField(decimal_places=2, max_digits=14)),
                        ("currency", models.CharField(max_length=3)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "organization",
                            models.ForeignKey(on_delete=models.PROTECT, to="rate_engine.organizations"),
                        ),
                    ],
                    options={
                        "db_table": "quotes_v2",
                        "managed": True,
                    },
                ),
                migrations.CreateModel(
                    name="QuoteLines",
                    fields=[
                        ("id", models.BigAutoField(primary_key=True, serialize=False)),
                        ("code", models.CharField(max_length=64)),
                        ("description", models.TextField()),
                        ("is_buy", models.BooleanField()),
                        ("is_sell", models.BooleanField()),
                        ("qty", models.DecimalField(decimal_places=3, max_digits=12)),
                        ("unit", models.CharField(max_length=16)),
                        ("unit_price", models.DecimalField(decimal_places=4, max_digits=12)),
                        ("extended_price", models.DecimalField(decimal_places=2, max_digits=12)),
                        ("currency", models.CharField(max_length=3)),
                        ("manual_rate_required", models.BooleanField(default=False)),
                        (
                            "quote",
                            models.ForeignKey(on_delete=models.CASCADE, related_name="lines", to="rate_engine.quotes"),
                        ),
                    ],
                    options={
                        "db_table": "quote_lines_v2",
                        "managed": True,
                    },
                ),
            ],
        ),
    ]

