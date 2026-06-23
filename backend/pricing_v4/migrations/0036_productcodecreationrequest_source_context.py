from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0045_add_rbac_scope_fields'),
        ('pricing_v4', '0035_add_approved_product_code_to_request'),
    ]

    operations = [
        migrations.AddField(
            model_name='productcodecreationrequest',
            name='source_context_json',
            field=models.JSONField(blank=True, help_text='Snapshot of source context for audit and fallback matching.', null=True),
        ),
        migrations.AddField(
            model_name='productcodecreationrequest',
            name='source_charge_line',
            field=models.ForeignKey(blank=True, help_text='SPOT charge line that originated this request, when available.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='product_code_creation_requests', to='quotes.spechargelinedb'),
        ),
        migrations.AddField(
            model_name='productcodecreationrequest',
            name='source_envelope',
            field=models.ForeignKey(blank=True, help_text='SPOT envelope that originated this request, when available.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='product_code_creation_requests', to='quotes.spotpricingenvelopedb'),
        ),
        migrations.AddField(
            model_name='productcodecreationrequest',
            name='source_quote',
            field=models.ForeignKey(blank=True, help_text='Quote linked to the originating SPOT envelope, when available.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='product_code_creation_requests', to='quotes.quote'),
        ),
        migrations.AddIndex(
            model_name='productcodecreationrequest',
            index=models.Index(fields=['status', 'source_envelope', 'source_charge_line'], name='pc_req_source_idx'),
        ),
    ]
