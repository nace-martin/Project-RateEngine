import json
from datetime import date
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from crm.models import Interaction, Opportunity, Task
from parties.models import Company


@pytest.mark.django_db
def test_rbac_crm_report_counts_scope_candidates():
    user = get_user_model().objects.create_user(username="crm-owner", password="password", role="sales")
    customer = Company.objects.create(name="Scoped Customer", is_customer=True, company_type="CUSTOMER")
    prospect = Company.objects.create(name="Prospect", is_customer=False, company_type="PROSPECT")
    opportunity = Opportunity.objects.create(
        company=customer,
        title="AIR lane",
        service_type="AIR",
        owner=user,
    )
    Opportunity.objects.create(
        company=prospect,
        title="SEA lane",
        service_type="SEA",
        owner=None,
    )
    Interaction.objects.create(
        company=customer,
        opportunity=opportunity,
        author=user,
        interaction_type=Interaction.InteractionType.CALL,
        summary="Sensitive call notes must not appear in report details.",
    )
    Task.objects.create(
        company=customer,
        opportunity=opportunity,
        owner=user,
        description="Sensitive task notes must not appear in report details.",
        due_date=date.today(),
    )

    stdout = StringIO()
    call_command("rbac_crm_report", "--format", "json", "--show-details", stdout=stdout)

    payload = json.loads(stdout.getvalue())
    assert payload["write_enabled"] is False
    assert payload["summary"]["total_records"] == 4
    assert payload["summary"]["with_owner_or_author"] == 3
    assert payload["summary"]["missing_owner_or_author"] == 1
    assert payload["summary"]["linked_to_company"] == 4
    assert payload["summary"]["linked_to_customer_company"] == 3
    assert payload["summary"]["with_org_branch_department_scope"] == 0
    assert payload["summary"]["likely_globally_accessible_today"] == 4
    assert payload["models"]["opportunity"]["future_scope_fields"] == ["owner", "company", "quotes"]

    details_json = json.dumps(payload["models"])
    assert "Sensitive call notes" not in details_json
    assert "Sensitive task notes" not in details_json
