from django.db import migrations, models


QUOTE_STATUS_CHOICES = [
    ("DRAFT", "Draft"),
    ("READY", "Ready"),
    ("FINALIZED", "Finalized"),
    ("SENT", "Sent to Customer"),
    ("ACCEPTED", "Accepted"),
    ("LOST", "Lost"),
    ("EXPIRED", "Expired"),
    ("CANCELLED", "Cancelled"),
]


def convert_incomplete_to_draft(apps, schema_editor):
    Quote = apps.get_model("quotes", "Quote")
    QuoteVersion = apps.get_model("quotes", "QuoteVersion")
    Quote.objects.filter(status="INCOMPLETE").update(status="DRAFT")
    QuoteVersion.objects.filter(status="INCOMPLETE").update(status="DRAFT")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0036_quote_opportunity"),
    ]

    operations = [
        migrations.RunPython(convert_incomplete_to_draft, noop_reverse),
        migrations.AlterField(
            model_name="quote",
            name="status",
            field=models.CharField(
                choices=QUOTE_STATUS_CHOICES,
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="quoteversion",
            name="status",
            field=models.CharField(
                choices=QUOTE_STATUS_CHOICES,
                default="DRAFT",
                help_text="Status of the quote at the time this version was created.",
                max_length=20,
            ),
        ),
    ]
