from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from parties.models import Company
from core.tests.helpers import create_location
from quotes.models import Quote
from crm.models import Opportunity, Interaction, Task
from crm.opportunity_auto_builder import OpportunityAutoBuilderService

User = get_user_model()

class OpportunityAutoBuilderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", email="test@example.com")
        self.customer = Company.objects.create(name="Daikin PNG", is_active=True)
        self.origin = create_location(code="POM", name="Port Moresby")
        self.destination = create_location(code="BNE", name="Brisbane")
        
        self.quote = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type="EXPORT",
            origin_location=self.origin,
            destination_location=self.destination,
            status=Quote.Status.DRAFT,
            created_by=self.user
        )

    def test_creates_opportunity_from_quote(self):
        opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        
        self.assertIsNotNone(opp)
        self.assertEqual(opp.company, self.customer)
        self.assertEqual(opp.title, "Air Export POM \u2192 BNE - Daikin PNG")
        self.assertEqual(opp.status, Opportunity.Status.NEW)
        
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.opportunity, opp)

    def test_reuses_existing_opportunity(self):
        opp1 = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        
        # New quote for same customer/route
        quote2 = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type="EXPORT",
            origin_location=self.origin,
            destination_location=self.destination,
            status=Quote.Status.DRAFT,
            created_by=self.user
        )
        
        opp2 = OpportunityAutoBuilderService.sync_from_quote(quote2)
        self.assertEqual(opp1.id, opp2.id)

    def test_deduplication_window(self):
        # Create an old opportunity (outside 14-day window)
        old_date = timezone.now() - timedelta(days=15)
        old_opp = Opportunity.objects.create(
            company=self.customer,
            title="Old Opp",
            service_type="AIR",
            direction="EXPORT",
            origin="POM",
            destination="BNE",
            status=Opportunity.Status.NEW,
            created_at=old_date
        )
        # Manually set created_at because auto_now_add=True
        Opportunity.objects.filter(id=old_opp.id).update(created_at=old_date)
        
        new_opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        self.assertNotEqual(new_opp.id, old_opp.id)

    def test_status_mapping(self):
        # Finalized -> Qualified
        self.quote.status = Quote.Status.FINALIZED
        opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        self.assertEqual(opp.status, Opportunity.Status.QUALIFIED)
        
        # Sent -> Quoted
        self.quote.status = Quote.Status.SENT
        opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        self.assertEqual(opp.status, Opportunity.Status.QUOTED)
        
        # Accepted -> Won
        self.quote.status = Quote.Status.ACCEPTED
        opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        self.assertEqual(opp.status, Opportunity.Status.WON)

    def test_interaction_recording(self):
        OpportunityAutoBuilderService.sync_from_quote(self.quote)
        
        interactions = Interaction.objects.filter(opportunity=self.quote.opportunity)
        self.assertEqual(interactions.count(), 1)
        self.assertTrue(interactions[0].is_system_generated)
        self.assertIn(f"quote_id={self.quote.id}", interactions[0].outcomes)

    def test_task_creation_on_sent(self):
        self.quote.status = Quote.Status.SENT
        opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        
        tasks = Task.objects.filter(opportunity=opp, status=Task.Status.PENDING)
        self.assertEqual(tasks.count(), 1)
        self.assertIn("Follow up", tasks[0].description)
        
        # Idempotency check: repeat sync should not duplicate task
        OpportunityAutoBuilderService.sync_from_quote(self.quote)
        self.assertEqual(tasks.count(), 1)

    def test_task_cleanup_on_won(self):
        # First send it
        self.quote.status = Quote.Status.SENT
        opp = OpportunityAutoBuilderService.sync_from_quote(self.quote)
        self.assertEqual(Task.objects.filter(opportunity=opp, status=Task.Status.PENDING).count(), 1)
        
        # Then win it
        self.quote.status = Quote.Status.ACCEPTED
        OpportunityAutoBuilderService.sync_from_quote(self.quote)
        
        self.assertEqual(Task.objects.filter(opportunity=opp, status=Task.Status.PENDING).count(), 0)
        self.assertEqual(Task.objects.filter(opportunity=opp, status=Task.Status.COMPLETED).count(), 1)
