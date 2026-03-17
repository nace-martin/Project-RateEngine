from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from services.models import ServiceComponent


class SyncV4ComponentsCommandTests(TestCase):
    def test_sync_v4_components_ensures_spot_components_exist(self):
        out = StringIO()

        call_command("sync_v4_components", stdout=out)

        self.assertTrue(ServiceComponent.objects.filter(code="SPOT_ORIGIN", mode="AIR", leg="ORIGIN").exists())
        self.assertTrue(ServiceComponent.objects.filter(code="SPOT_FREIGHT", mode="AIR", leg="MAIN").exists())
        self.assertTrue(
            ServiceComponent.objects.filter(code="SPOT_DEST", mode="AIR", leg="DESTINATION").exists()
        )
        self.assertTrue(
            ServiceComponent.objects.filter(
                code="SPOT_CHARGE",
                description="Spot Additional Charge",
                mode="AIR",
                leg="MAIN",
                category="ACCESSORIAL",
            ).exists()
        )
        self.assertIn("SPOT created", out.getvalue())
