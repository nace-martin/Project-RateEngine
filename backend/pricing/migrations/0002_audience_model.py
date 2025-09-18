
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Audience',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('party_type', models.CharField(choices=[('CUSTOMER', 'Customer'), ('AGENT', 'Agent')], max_length=32)),
                ('region', models.CharField(choices=[('PNG', 'Papua New Guinea'), ('AU', 'Australia'), ('USD', 'United States Dollar'), ('OVERSEAS', 'Overseas')], max_length=32)),
                ('settlement', models.CharField(choices=[('PREPAID', 'Prepaid'), ('COLLECT', 'Collect')], max_length=32)),
                ('code', models.CharField(max_length=128, unique=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'audiences',
                'unique_together': {('party_type', 'region', 'settlement')},
            },
        ),
        migrations.RenameField(
            model_name='ratecards',
            old_name='audience',
            new_name='audience_old',
        ),
        migrations.AddField(
            model_name='ratecards',
            name='audience',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='pricing.audience'),
        ),
    ]
