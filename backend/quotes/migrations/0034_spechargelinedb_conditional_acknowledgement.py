from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('quotes', '0033_spechargelinedb_source_line_identity'),
    ]

    operations = [
        migrations.AddField(
            model_name='spechargelinedb',
            name='conditional_acknowledged',
            field=models.BooleanField(default=False, help_text='True when a reviewer explicitly kept this conditional source charge in the quote.'),
        ),
        migrations.AddField(
            model_name='spechargelinedb',
            name='conditional_acknowledged_at',
            field=models.DateTimeField(blank=True, help_text='Timestamp when the conditional charge was acknowledged.', null=True),
        ),
        migrations.AddField(
            model_name='spechargelinedb',
            name='conditional_acknowledged_by',
            field=models.ForeignKey(blank=True, help_text='User who acknowledged keeping this conditional charge.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
    ]
