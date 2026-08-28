from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import Role, UserMembership
from crm.models import Interaction, Opportunity, Task
from crm.services import (
    mark_opportunity_lost,
    mark_opportunity_quoted,
    mark_opportunity_won,
)
from parties.models import Branch, Company, Department, Organization


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="crm-user", password="password", role="sales")


@pytest.fixture
def company(db):
    return Company.objects.create(name="CRM Customer", is_customer=True, company_type="CUSTOMER")


@pytest.fixture
def opportunity(company, user):
    return Opportunity.objects.create(
        company=company,
        title="Weekly BNE-POM import lane",
        service_type="AIR",
        direction="IMPORT",
        scope="A2D",
        origin="BNE",
        destination="POM",
        estimated_weight_kg=Decimal("120.50"),
        estimated_volume_cbm=Decimal("1.250"),
        estimated_frequency="Weekly",
        estimated_revenue=Decimal("2500.00"),
        estimated_currency="PGK",
        owner=user,
    )


def create_scope_fixture(*, suffix=""):
    organization = Organization.objects.create(
        name=f"CRM Scope Org {suffix}".strip(),
        slug=f"crm-scope-org-{suffix or 'default'}",
        is_active=True,
    )
    branch = Branch.objects.create(organization=organization, code=f"POM{suffix}"[:16], name="Port Moresby")
    department = Department.objects.create(
        organization=organization,
        branch=branch,
        code=f"AIR{suffix}"[:24],
        name="Air Freight",
    )
    return organization, branch, department


def create_role(code="sales"):
    return Role.objects.create(code=code, name=code.title(), is_system=True)


@pytest.mark.django_db
def test_crm_model_creation(company, user):
    opportunity = Opportunity.objects.create(
        company=company,
        title="Domestic distribution",
        service_type="DOMESTIC",
        direction="DOMESTIC",
        priority=Opportunity.Priority.HIGH,
        owner=user,
    )
    interaction = Interaction.objects.create(
        company=company,
        opportunity=opportunity,
        author=user,
        interaction_type=Interaction.InteractionType.CALL,
        summary="Discussed weekly distribution needs.",
    )
    task = Task.objects.create(
        company=company,
        opportunity=opportunity,
        owner=user,
        description="Prepare distribution estimate.",
        due_date=date.today() + timedelta(days=1),
    )

    assert opportunity.status == Opportunity.Status.NEW
    assert interaction.summary
    assert task.status == Task.Status.PENDING


@pytest.mark.django_db
def test_opportunity_api_create_populates_scope_from_single_active_membership(company, user):
    organization, branch, department = create_scope_fixture(suffix="1")
    UserMembership.objects.create(
        user=user,
        organization=organization,
        branch=branch,
        department=department,
        role=create_role("sales-1"),
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/crm/opportunities/",
        {
            "company": str(company.id),
            "title": "Scoped CRM opportunity",
            "service_type": "AIR",
            "priority": Opportunity.Priority.MEDIUM,
        },
        format="json",
    )

    assert response.status_code == 201
    opportunity = Opportunity.objects.get(title="Scoped CRM opportunity")
    assert opportunity.organization == organization
    assert opportunity.branch == branch
    assert opportunity.department == department


@pytest.mark.django_db
def test_interaction_and_task_create_inherit_opportunity_scope(company, user):
    organization, branch, department = create_scope_fixture(suffix="2")
    opportunity = Opportunity.objects.create(
        company=company,
        title="Scoped parent opportunity",
        service_type="AIR",
        owner=user,
        organization=organization,
        branch=branch,
        department=department,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    interaction_response = client.post(
        "/api/v3/crm/interactions/",
        {
            "company": str(company.id),
            "opportunity": str(opportunity.id),
            "interaction_type": Interaction.InteractionType.CALL,
            "summary": "Called customer.",
        },
        format="json",
    )
    task_response = client.post(
        "/api/v3/crm/tasks/",
        {
            "opportunity": str(opportunity.id),
            "description": "Follow up.",
            "due_date": str(date.today() + timedelta(days=1)),
        },
        format="json",
    )

    assert interaction_response.status_code == 201
    assert task_response.status_code == 201
    interaction = Interaction.objects.get(summary="Called customer.")
    task = Task.objects.get(description="Follow up.")
    assert interaction.organization == organization
    assert interaction.branch == branch
    assert interaction.department == department
    assert task.organization == organization
    assert task.branch == branch
    assert task.department == department


@pytest.mark.django_db
def test_opportunity_create_with_multiple_memberships_sets_only_shared_scope(company, user):
    organization, branch, department = create_scope_fixture(suffix="3")
    other_branch = Branch.objects.create(organization=organization, code="LAE", name="Lae")
    other_department = Department.objects.create(
        organization=organization,
        branch=other_branch,
        code="SEA",
        name="Sea Freight",
    )
    role = create_role("sales-3")
    UserMembership.objects.create(
        user=user,
        organization=organization,
        branch=branch,
        department=department,
        role=role,
        is_primary=True,
    )
    UserMembership.objects.create(
        user=user,
        organization=organization,
        branch=other_branch,
        department=other_department,
        role=role,
        is_primary=False,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/crm/opportunities/",
        {
            "company": str(company.id),
            "title": "Ambiguous CRM opportunity",
            "service_type": "AIR",
            "priority": Opportunity.Priority.MEDIUM,
        },
        format="json",
    )

    assert response.status_code == 201
    opportunity = Opportunity.objects.get(title="Ambiguous CRM opportunity")
    assert opportunity.organization == organization
    assert opportunity.branch is None
    assert opportunity.department is None


@pytest.mark.django_db
def test_membership_fallback_does_not_mix_scope_across_parent_organization(company, user):
    parent_org = Organization.objects.create(name="Parent Org", slug="parent-org", is_active=True)
    membership_org, membership_branch, membership_department = create_scope_fixture(suffix="4")
    company.organization = parent_org
    company.save(update_fields=["organization", "updated_at"])
    UserMembership.objects.create(
        user=user,
        organization=membership_org,
        branch=membership_branch,
        department=membership_department,
        role=create_role("sales-4"),
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/crm/opportunities/",
        {
            "company": str(company.id),
            "title": "Parent org only opportunity",
            "service_type": "AIR",
            "priority": Opportunity.Priority.MEDIUM,
        },
        format="json",
    )

    assert response.status_code == 201
    opportunity = Opportunity.objects.get(title="Parent org only opportunity")
    assert opportunity.organization == parent_org
    assert opportunity.branch is None
    assert opportunity.department is None


@pytest.mark.django_db
def test_task_requires_company_or_opportunity(user):
    task = Task(
        owner=user,
        description="Unlinked task",
        due_date=date.today(),
    )

    with pytest.raises(ValidationError):
        task.full_clean()


@pytest.mark.django_db
def test_interaction_updates_company_and_opportunity_timestamps(company, user, opportunity):
    Interaction.objects.create(
        company=company,
        opportunity=opportunity,
        author=user,
        interaction_type=Interaction.InteractionType.MEETING,
        summary="Met customer about import workflow.",
    )

    company.refresh_from_db()
    opportunity.refresh_from_db()
    assert company.last_interaction_at is not None
    assert opportunity.last_activity_at == company.last_interaction_at


@pytest.mark.django_db
def test_lifecycle_helpers_create_system_interactions(opportunity, user):
    quoted = mark_opportunity_quoted(opportunity, actor=user)
    assert quoted.status == Opportunity.Status.QUOTED

    won = mark_opportunity_won(
        quoted,
        actor=user,
        reason="Customer approved the import file.",
        source_type="IMPORT_JOB_CREATED",
        source_id="IMP-001",
    )
    assert won.status == Opportunity.Status.WON
    assert won.won_by == user
    assert won.won_reason == "Customer approved the import file."

    lost = mark_opportunity_lost(won, actor=user, reason="Customer deferred project.")
    assert lost.status == Opportunity.Status.LOST
    assert lost.lost_reason == "Customer deferred project."

    event_types = set(opportunity.interactions.values_list("system_event_type", flat=True))
    assert event_types == {"OPPORTUNITY_QUOTED", "OPPORTUNITY_WON", "OPPORTUNITY_LOST"}


@pytest.mark.django_db
def test_mark_quoted_does_not_override_terminal_status(opportunity, user):
    opportunity.status = Opportunity.Status.WON
    opportunity.save(update_fields=["status", "updated_at"])

    quoted = mark_opportunity_quoted(opportunity, actor=user)

    assert quoted.status == Opportunity.Status.WON
    assert quoted.interactions.filter(system_event_type="OPPORTUNITY_QUOTED").exists()


@pytest.mark.django_db
def test_opportunity_workflow_actions_use_lifecycle_helpers(opportunity, user):
    client = APIClient()
    client.force_authenticate(user=user)

    qualified_response = client.post(f"/api/v3/crm/opportunities/{opportunity.id}/mark_qualified/")
    assert qualified_response.status_code == 200
    assert qualified_response.json()["status"] == Opportunity.Status.QUALIFIED

    won_response = client.post(
        f"/api/v3/crm/opportunities/{opportunity.id}/mark_won/",
        {"won_reason": "Customer confirmed manually."},
        format="json",
    )
    assert won_response.status_code == 200
    assert won_response.json()["status"] == Opportunity.Status.WON
    opportunity.refresh_from_db()
    assert opportunity.won_by == user
    assert opportunity.won_reason == "Customer confirmed manually."
    assert opportunity.interactions.filter(
        system_event_type="OPPORTUNITY_WON",
        outcomes__contains="Source: MANUAL",
    ).exists()

    lost_response = client.post(
        f"/api/v3/crm/opportunities/{opportunity.id}/mark_lost/",
        {"lost_reason": "Customer chose another provider."},
        format="json",
    )
    assert lost_response.status_code == 200
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.LOST
    assert opportunity.lost_reason == "Customer chose another provider."
    assert opportunity.won_at is None
    assert opportunity.won_by is None


@pytest.mark.django_db
def test_opportunity_api_rejects_direct_terminal_status_on_create(company, user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/crm/opportunities/",
        {
            "company": str(company.id),
            "title": "Unsafe won status",
            "service_type": "AIR",
            "origin": "BNE",
            "destination": "POM",
            "status": Opportunity.Status.WON,
            "priority": Opportunity.Priority.MEDIUM,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "status" in response.json()
    assert not Opportunity.objects.filter(title="Unsafe won status").exists()


@pytest.mark.django_db
def test_opportunity_api_rejects_direct_terminal_status_on_update(opportunity, user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.patch(
        f"/api/v3/crm/opportunities/{opportunity.id}/",
        {"status": Opportunity.Status.LOST},
        format="json",
    )

    assert response.status_code == 400
    assert "status" in response.json()
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.NEW
    assert opportunity.lost_reason == ""


@pytest.mark.django_db
def test_opportunity_api_accepts_transport_service_type(company, user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/crm/opportunities/",
        {
            "company": str(company.id),
            "title": "Local delivery follow-up",
            "service_type": "TRANSPORT",
            "origin": "Lae",
            "destination": "Port Moresby",
            "status": Opportunity.Status.NEW,
            "priority": Opportunity.Priority.MEDIUM,
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["service_type"] == "TRANSPORT"


@pytest.mark.django_db
def test_mark_lost_requires_reason(opportunity, user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        f"/api/v3/crm/opportunities/{opportunity.id}/mark_lost/",
        {"lost_reason": ""},
        format="json",
    )

    assert response.status_code == 400
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.NEW


@pytest.mark.django_db
def test_task_complete_action_sets_completion_fields(company, opportunity, user):
    task = Task.objects.create(
        company=company,
        opportunity=opportunity,
        owner=user,
        description="Follow up with customer.",
        due_date=date.today(),
    )
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(f"/api/v3/crm/tasks/{task.id}/complete/")

    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.COMPLETED
    assert task.completed_at is not None
    assert task.completed_by == user


@pytest.mark.django_db
def test_import_opportunity_can_be_won_without_shipment(opportunity, user):
    won = mark_opportunity_won(
        opportunity,
        actor=user,
        reason="Agent pre-alert received and import file opened.",
        source_type="AGENT_PREALERT_RECEIVED",
    )

    assert won.direction == "IMPORT"
    assert won.status == Opportunity.Status.WON
    assert won.interactions.filter(system_event_type="OPPORTUNITY_WON").exists()
