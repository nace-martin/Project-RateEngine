# backend/quotes/tests/test_state_machine.py
"""
Quote State Machine Tests

Tests for quote lifecycle transitions and edit-blocking functionality.
"""

import pytest
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from quotes.models import Quote, QuoteVersion
from quotes.state_machine import (
    QuoteStateMachine,
    QuoteStateError,
    is_quote_editable,
    get_status_display_info,
    VALID_TRANSITIONS,
    LOCKED_STATES,
)
from parties.models import Company, Contact
from core.models import Country, City, Airport, Location, Currency, FxSnapshot, Policy


pytestmark = pytest.mark.django_db


# --- Fixtures ---

@pytest.fixture
def user():
    User = get_user_model()
    return User.objects.create_user(
        username="test_user",
        email="test@example.com",
        password="testpass",
        is_staff=True,
        role='manager'
    )


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def setup_basic_data():
    """Create basic data needed for quote creation."""
    # Country and currency
    country_pg, _ = Country.objects.get_or_create(code='PG', defaults={'name': 'Papua New Guinea'})
    country_au, _ = Country.objects.get_or_create(code='AU', defaults={'name': 'Australia'})
    
    Currency.objects.get_or_create(code='PGK', defaults={'name': 'Papua New Guinean Kina'})
    Currency.objects.get_or_create(code='AUD', defaults={'name': 'Australian Dollar'})
    
    # Cities and airports
    city_pom, _ = City.objects.get_or_create(name='Port Moresby', country=country_pg)
    city_bne, _ = City.objects.get_or_create(name='Brisbane', country=country_au)
    
    airport_pom, _ = Airport.objects.get_or_create(iata_code='POM', defaults={'name': 'Jacksons Intl', 'city': city_pom})
    airport_bne, _ = Airport.objects.get_or_create(iata_code='BNE', defaults={'name': 'Brisbane Intl', 'city': city_bne})
    
    # Locations
    loc_pom, _ = Location.objects.get_or_create(
        airport=airport_pom,
        defaults={'name': 'Port Moresby', 'code': 'POM', 'country': country_pg, 'city': city_pom}
    )
    loc_bne, _ = Location.objects.get_or_create(
        airport=airport_bne,
        defaults={'name': 'Brisbane', 'code': 'BNE', 'country': country_au, 'city': city_bne}
    )
    
    # FX and Policy
    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source='test',
        rates={'AUD': {'tt_buy': '2.50', 'tt_sell': '2.60'}}
    )
    Policy.objects.get_or_create(
        name='Test Policy',
        defaults={
            'margin_pct': Decimal('0.15'),
            'caf_import_pct': Decimal('0.05'),
            'effective_from': timezone.now(),
            'is_active': True,
        }
    )
    
    # Customer
    customer, _ = Company.objects.get_or_create(
        name='Test Customer',
        defaults={'is_customer': True}
    )
    contact, _ = Contact.objects.get_or_create(
        company=customer,
        email='test@customer.com',
        defaults={'first_name': 'Test', 'last_name': 'User'}
    )
    
    return {
        'customer': customer,
        'contact': contact,
        'origin_location': loc_bne,
        'destination_location': loc_pom,
    }


@pytest.fixture
def draft_quote(user, setup_basic_data):
    """Create a DRAFT quote for testing."""
    return Quote.objects.create(
        customer=setup_basic_data['customer'],
        contact=setup_basic_data['contact'],
        mode='AIR',
        shipment_type='IMPORT',
        incoterm='DAP',
        payment_term='PREPAID',
        service_scope='D2D',
        output_currency='PGK',
        origin_location=setup_basic_data['origin_location'],
        destination_location=setup_basic_data['destination_location'],
        status=Quote.Status.DRAFT,
        created_by=user,
    )


@pytest.fixture
def finalized_quote(user, setup_basic_data):
    """Create a FINALIZED quote for testing."""
    quote = Quote.objects.create(
        customer=setup_basic_data['customer'],
        contact=setup_basic_data['contact'],
        mode='AIR',
        shipment_type='IMPORT',
        incoterm='DAP',
        payment_term='PREPAID',
        service_scope='D2D',
        output_currency='PGK',
        origin_location=setup_basic_data['origin_location'],
        destination_location=setup_basic_data['destination_location'],
        status=Quote.Status.FINALIZED,
        finalized_at=timezone.now(),
        finalized_by=user,
        created_by=user,
    )
    return quote


# --- State Machine Unit Tests ---

class TestQuoteStateMachine:
    """Unit tests for the QuoteStateMachine class."""
    
    def test_current_state(self, draft_quote):
        machine = QuoteStateMachine(draft_quote)
        assert machine.current_state == Quote.Status.DRAFT
    
    def test_draft_is_editable(self, draft_quote):
        machine = QuoteStateMachine(draft_quote)
        assert machine.is_editable is True
    
    def test_finalized_is_not_editable(self, finalized_quote):
        machine = QuoteStateMachine(finalized_quote)
        assert machine.is_editable is False
    
    def test_available_transitions_from_draft(self, draft_quote):
        machine = QuoteStateMachine(draft_quote)
        assert Quote.Status.FINALIZED in machine.available_transitions
        assert Quote.Status.SENT not in machine.available_transitions
    
    def test_available_transitions_from_finalized(self, finalized_quote):
        machine = QuoteStateMachine(finalized_quote)
        assert Quote.Status.SENT in machine.available_transitions
        assert Quote.Status.DRAFT not in machine.available_transitions
    
    def test_can_transition_draft_to_finalized(self, draft_quote):
        machine = QuoteStateMachine(draft_quote)
        assert machine.can_transition_to(Quote.Status.FINALIZED) is True
    
    def test_cannot_transition_draft_to_sent(self, draft_quote):
        machine = QuoteStateMachine(draft_quote)
        assert machine.can_transition_to(Quote.Status.SENT) is False
    
    def test_successful_finalize_transition(self, draft_quote, user):
        machine = QuoteStateMachine(draft_quote)
        success, error = machine.finalize(user=user)
        
        assert success is True
        assert error is None
        draft_quote.refresh_from_db()
        assert draft_quote.status == Quote.Status.FINALIZED
        assert draft_quote.finalized_at is not None
        assert draft_quote.finalized_by == user
    
    def test_successful_send_transition(self, finalized_quote, user):
        machine = QuoteStateMachine(finalized_quote)
        success, error = machine.mark_sent(user=user)
        
        assert success is True
        assert error is None
        finalized_quote.refresh_from_db()
        assert finalized_quote.status == Quote.Status.SENT
        assert finalized_quote.sent_at is not None
        assert finalized_quote.sent_by == user
    
    def test_invalid_transition_returns_error(self, draft_quote, user):
        machine = QuoteStateMachine(draft_quote)
        success, error = machine.transition_to(Quote.Status.SENT, user)
        
        assert success is False
        assert error is not None
        assert 'Cannot transition' in error
        draft_quote.refresh_from_db()
        assert draft_quote.status == Quote.Status.DRAFT  # Unchanged


# --- Utility Function Tests ---

class TestUtilityFunctions:
    """Tests for utility functions."""
    
    def test_is_quote_editable_draft(self, draft_quote):
        assert is_quote_editable(draft_quote) is True
    
    def test_is_quote_editable_finalized(self, finalized_quote):
        assert is_quote_editable(finalized_quote) is False
    
    def test_is_quote_editable_sent(self, finalized_quote, user):
        # Transition to SENT
        machine = QuoteStateMachine(finalized_quote)
        machine.mark_sent(user)
        finalized_quote.refresh_from_db()
        
        assert is_quote_editable(finalized_quote) is False
    
    def test_get_status_display_info_draft(self):
        info = get_status_display_info(Quote.Status.DRAFT)
        assert info['label'] == 'Draft'
        assert info['editable'] is True
    
    def test_get_status_display_info_finalized(self):
        info = get_status_display_info(Quote.Status.FINALIZED)
        assert info['label'] == 'Finalized'
        assert info['editable'] is False
    
    def test_locked_states_configuration(self):
        assert Quote.Status.FINALIZED in LOCKED_STATES
        assert Quote.Status.SENT in LOCKED_STATES
        assert Quote.Status.DRAFT not in LOCKED_STATES


# --- API Edit-Blocking Tests ---

class TestEditBlockingAPI:
    """API tests for edit-blocking functionality."""
    
    def test_transition_endpoint_get(self, api_client, draft_quote):
        url = f'/api/v3/quotes/{draft_quote.id}/transition/'
        response = api_client.get(url)
        
        assert response.status_code == 200
        assert response.data['current_status'] == 'DRAFT'
        assert response.data['is_editable'] is True
        assert 'FINALIZED' in response.data['available_transitions']
    
    def test_transition_endpoint_finalize(self, api_client, draft_quote):
        url = f'/api/v3/quotes/{draft_quote.id}/transition/'
        response = api_client.post(url, {'action': 'finalize'}, format='json')
        
        assert response.status_code == 200
        assert response.data['status'] == 'FINALIZED'
        
        draft_quote.refresh_from_db()
        assert draft_quote.status == Quote.Status.FINALIZED
    
    def test_transition_endpoint_send(self, api_client, finalized_quote):
        url = f'/api/v3/quotes/{finalized_quote.id}/transition/'
        response = api_client.post(url, {'action': 'send'}, format='json')
        
        assert response.status_code == 200
        assert response.data['status'] == 'SENT'
    
    def test_transition_invalid_action(self, api_client, draft_quote):
        url = f'/api/v3/quotes/{draft_quote.id}/transition/'
        response = api_client.post(url, {'action': 'invalid'}, format='json')
        
        assert response.status_code == 400
        assert 'Invalid action' in response.data['detail']
    
    def test_transition_invalid_state_change(self, api_client, draft_quote):
        # Try to mark as sent without finalizing first
        url = f'/api/v3/quotes/{draft_quote.id}/transition/'
        response = api_client.post(url, {'action': 'send'}, format='json')
        
        assert response.status_code == 400
        assert 'Cannot transition' in response.data['detail']
    
    @pytest.mark.skip(reason="Clone view requires Quote model fields (pickup_suburb) that need migrations to be current")
    def test_clone_finalized_quote(self, api_client, finalized_quote):
        # Add required fields for clone
        finalized_quote.request_details_json = {}
        finalized_quote.save()
        
        url = f'/api/v3/quotes/{finalized_quote.id}/clone/'
        response = api_client.post(url, format='json')
        
        assert response.status_code == 201
        assert response.data['status'] == 'DRAFT'
        assert 'cloned_from' in response.data
        assert response.data['cloned_from']['id'] == str(finalized_quote.id)
    
    def test_clone_draft_quote_fails(self, api_client, draft_quote):
        url = f'/api/v3/quotes/{draft_quote.id}/clone/'
        response = api_client.post(url, format='json')
        
        assert response.status_code == 400
        assert 'Cannot clone' in response.data['detail']
    
    def test_version_create_blocked_for_finalized(self, api_client, finalized_quote):
        """Test that creating versions for finalized quotes is blocked."""
        url = f'/api/v3/quotes/{finalized_quote.id}/versions/'
        response = api_client.post(url, {'charges': []}, format='json')
        
        assert response.status_code == 403
        assert 'locked for editing' in response.data['detail']
