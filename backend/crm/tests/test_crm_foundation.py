from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from crm.models import Interaction, Opportunity, Task
from crm.services import (
    resolve_quote_opportunity,
    mark_opportunity_lost,
    mark_opportunity_quoted,
    mark_opportunity_won,
)
from parties.models import Company
from quotes.models import Quote
from quotes.state_machine import QuoteStateMachine


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


def create_quote(company, opportunity, user, *, status=Quote.Status.DRAFT, shipment_type=Quote.ShipmentType.IMPORT):
    return Quote.objects.create(
        customer=company,
        opportunity=opportunity,
        created_by=user,
        mode="AIR",
        shipment_type=shipment_type,
        status=status,
    )


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
def test_quote_opportunity_helper_creates_quoted_status_for_finalized_quote(company, user):
    opportunity, was_created = resolve_quote_opportunity(
        customer=company,
        mode="AIR",
        shipment_type="EXPORT",
        service_scope="A2A",
        actor=user,
        quote_status=Quote.Status.FINALIZED,
    )

    assert was_created is True
    assert opportunity.status == Opportunity.Status.QUOTED
    assert opportunity.service_type == "AIR"
    assert opportunity.direction == "EXPORT"
    assert opportunity.scope == "A2A"


@pytest.mark.django_db
def test_quote_opportunity_helper_maps_land_to_transport_without_domestic_service_type(company, user):
    opportunity, was_created = resolve_quote_opportunity(
        customer=company,
        mode="LAND",
        shipment_type="DOMESTIC",
        service_scope="D2D",
        actor=user,
        quote_status=Quote.Status.DRAFT,
    )

    assert was_created is True
    assert opportunity.status == Opportunity.Status.NEW
    assert opportunity.service_type == "TRANSPORT"
    assert opportunity.direction == "DOMESTIC"
    assert not Opportunity.objects.filter(service_type="DOMESTIC").exists()


@pytest.mark.django_db
def test_quote_can_link_to_opportunity(company, opportunity, user):
    quote = Quote.objects.create(
        customer=company,
        opportunity=opportunity,
        created_by=user,
        mode="AIR",
        shipment_type=Quote.ShipmentType.IMPORT,
    )

    assert quote.opportunity == opportunity
    assert opportunity.quotes.get() == quote


@pytest.mark.django_db
def test_quote_api_filters_by_opportunity(company, opportunity, user):
    other_opportunity = Opportunity.objects.create(
        company=company,
        title="Unrelated lane",
        service_type="SEA",
        origin="LAE",
        destination="POM",
        owner=user,
    )
    matching_quote = create_quote(company, opportunity, user)
    create_quote(company, other_opportunity, user)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/v3/quotes/?opportunity={opportunity.id}")

    assert response.status_code == 200
    payload = response.json()
    results = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    assert [row["id"] for row in results] == [str(matching_quote.id)]


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


@pytest.mark.django_db
def test_linked_quote_finalize_marks_new_opportunity_quoted(company, opportunity, user):
    quote = create_quote(company, opportunity, user)

    success, error = QuoteStateMachine(quote).finalize(user=user)

    assert success, error
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.QUOTED
    assert opportunity.interactions.filter(system_event_type="QUOTE_FINALIZED").count() == 1
    assert opportunity.interactions.filter(system_event_type="OPPORTUNITY_QUOTED").count() == 1


@pytest.mark.django_db
def test_linked_quote_sent_marks_qualified_opportunity_quoted_without_duplicate(company, opportunity, user):
    opportunity.status = Opportunity.Status.QUALIFIED
    opportunity.save(update_fields=["status", "updated_at"])
    quote = create_quote(company, opportunity, user)
    machine = QuoteStateMachine(quote)
    success, error = machine.finalize(user=user)
    assert success, error

    success, error = machine.mark_sent(user=user)

    assert success, error
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.QUOTED
    assert opportunity.interactions.filter(system_event_type="QUOTE_SENT").count() == 1
    assert opportunity.interactions.filter(system_event_type="OPPORTUNITY_QUOTED").count() == 1


@pytest.mark.django_db
def test_quoted_event_does_not_overwrite_won_or_lost_opportunity(company, opportunity, user):
    for terminal_status in (Opportunity.Status.WON, Opportunity.Status.LOST):
        opportunity.status = terminal_status
        opportunity.save(update_fields=["status", "updated_at"])
        quote = create_quote(company, opportunity, user)

        success, error = QuoteStateMachine(quote).finalize(user=user)

        assert success, error
        opportunity.refresh_from_db()
        assert opportunity.status == terminal_status


@pytest.mark.django_db
def test_quote_accepted_marks_linked_opportunity_won(company, opportunity, user):
    quote = create_quote(company, opportunity, user)
    machine = QuoteStateMachine(quote)
    assert machine.finalize(user=user)[0]
    assert machine.mark_sent(user=user)[0]

    success, error = machine.mark_won(user=user)

    assert success, error
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.WON
    assert opportunity.won_by == user
    assert "accepted" in opportunity.won_reason.lower()
    assert opportunity.interactions.filter(system_event_type="QUOTE_ACCEPTED").count() == 1
    assert opportunity.interactions.filter(system_event_type="OPPORTUNITY_WON").count() == 1


@pytest.mark.django_db
def test_import_quote_opportunity_can_be_won_without_shipment(company, opportunity, user):
    opportunity.direction = "IMPORT"
    opportunity.save(update_fields=["direction", "updated_at"])
    quote = create_quote(company, opportunity, user, shipment_type=Quote.ShipmentType.IMPORT)
    machine = QuoteStateMachine(quote)
    assert machine.finalize(user=user)[0]
    assert machine.mark_sent(user=user)[0]

    success, error = machine.mark_won(user=user)

    assert success, error
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.WON


@pytest.mark.django_db
def test_quote_lifecycle_does_not_duplicate_system_interactions(company, opportunity, user):
    quote = create_quote(company, opportunity, user)
    machine = QuoteStateMachine(quote)
    assert machine.finalize(user=user)[0]
    assert machine.mark_sent(user=user)[0]

    second_success, _ = machine.mark_sent(user=user)

    assert second_success is False
    assert opportunity.interactions.filter(system_event_type="QUOTE_SENT").count() == 1
    assert opportunity.interactions.filter(system_event_type="OPPORTUNITY_QUOTED").count() == 1


@pytest.mark.django_db
def test_lost_quote_does_not_mark_opportunity_lost_when_other_quote_active(company, opportunity, user):
    lost_quote = create_quote(company, opportunity, user, status=Quote.Status.SENT)
    create_quote(company, opportunity, user, status=Quote.Status.DRAFT)

    success, error = QuoteStateMachine(lost_quote).mark_lost(user=user)

    assert success, error
    opportunity.refresh_from_db()
    assert opportunity.status == Opportunity.Status.NEW
    assert opportunity.interactions.filter(system_event_type="QUOTE_LOST").count() == 1
    assert opportunity.interactions.filter(system_event_type="OPPORTUNITY_LOST").count() == 0
