# backend/pricing_v4/management/commands/seed_export_pom_bne.py
"""
Seed ProductCodes and rates for the first corridor: Export Air D2A Prepaid POM→BNE

Rule 8: ProductCode must exist before any rate row
Rule 9: One corridor must work end-to-end before expanding
"""

from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import ProductCode, ExportCOGS, ExportSellRate


class Command(BaseCommand):
    help = 'Seed ProductCodes and rates for Export D2A POM→BNE corridor'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("Seeding Export D2A POM→BNE Corridor")
        self.stdout.write("=" * 60)
        
        with transaction.atomic():
            self._seed_product_codes()
            self._seed_export_cogs()
            self._seed_export_sell_rates()
        
        self.stdout.write(self.style.SUCCESS("\n✓ Corridor seeding complete!"))
    
    def _seed_product_codes(self):
        """
        Seed ProductCodes for Export domain.
        
        ID Range: 1xxx
        Rule 8: ProductCodes must exist FIRST.
        """
        self.stdout.write("\n--- Seeding ProductCodes (1xxx Export) ---")
        
        # Export ProductCode definitions
        export_codes = [
            # 1001-1009: Freight
            {
                'id': 1001,
                'code': 'EXP-FRT-AIR',
                'description': 'Export Air Freight',
                'category': ProductCode.CATEGORY_FREIGHT,
                'is_gst_applicable': False,  # Export = GST-free
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4100',
                'gl_cost_code': '5100',
                'default_unit': ProductCode.UNIT_KG,
            },
            # 1010-1019: Documentation
            {
                'id': 1010,
                'code': 'EXP-DOC',
                'description': 'Export Documentation Fee',
                'category': ProductCode.CATEGORY_DOCUMENTATION,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4200',
                'gl_cost_code': '5200',
                'default_unit': ProductCode.UNIT_SHIPMENT,
            },
            {
                'id': 1011,
                'code': 'EXP-AWB',
                'description': 'Export AWB Fee',
                'category': ProductCode.CATEGORY_DOCUMENTATION,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4200',
                'gl_cost_code': '5200',
                'default_unit': ProductCode.UNIT_SHIPMENT,
            },
            # 1020-1029: Clearance & Agency
            {
                'id': 1020,
                'code': 'EXP-CLEAR',
                'description': 'Export Customs Clearance',
                'category': ProductCode.CATEGORY_CLEARANCE,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4300',
                'gl_cost_code': '5300',
                'default_unit': ProductCode.UNIT_SHIPMENT,
            },
            {
                'id': 1021,
                'code': 'EXP-AGENCY',
                'description': 'Export Agency Fee',
                'category': ProductCode.CATEGORY_AGENCY,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4300',
                'gl_cost_code': '5300',
                'default_unit': ProductCode.UNIT_SHIPMENT,
            },
            # 1030-1039: Handling & Terminal
            {
                'id': 1030,
                'code': 'EXP-TERM',
                'description': 'Export Terminal Handling Fee',
                'category': ProductCode.CATEGORY_HANDLING,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4400',
                'gl_cost_code': '5400',
                'default_unit': ProductCode.UNIT_SHIPMENT,
            },
            {
                'id': 1031,
                'code': 'EXP-BUILDUP',
                'description': 'Export Build-Up Fee',
                'category': ProductCode.CATEGORY_HANDLING,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4400',
                'gl_cost_code': '5400',
                'default_unit': ProductCode.UNIT_KG,
            },
            # 1040-1049: Screening & Security
            {
                'id': 1040,
                'code': 'EXP-SCREEN',
                'description': 'Export Security Screening',
                'category': ProductCode.CATEGORY_SCREENING,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4400',
                'gl_cost_code': '5400',
                'default_unit': ProductCode.UNIT_KG,
            },
            # 1050-1059: Cartage (Pickup)
            {
                'id': 1050,
                'code': 'EXP-PICKUP',
                'description': 'Export Pickup/Collection',
                'category': ProductCode.CATEGORY_CARTAGE,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4500',
                'gl_cost_code': '5500',
                'default_unit': ProductCode.UNIT_KG,
            },
        ]
        
        for code_data in export_codes:
            obj, created = ProductCode.objects.update_or_create(
                id=code_data['id'],
                defaults={
                    'code': code_data['code'],
                    'description': code_data['description'],
                    'domain': ProductCode.DOMAIN_EXPORT,
                    'category': code_data['category'],
                    'is_gst_applicable': code_data['is_gst_applicable'],
                    'gst_rate': code_data['gst_rate'],
                    'gl_revenue_code': code_data['gl_revenue_code'],
                    'gl_cost_code': code_data['gl_cost_code'],
                    'default_unit': code_data['default_unit'],
                }
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {obj.id} - {obj.code}")
    
    def _seed_export_cogs(self):
        """
        Seed ExportCOGS for POM→BNE corridor.
        
        Source: PX International rate card (what EFM pays)
        """
        self.stdout.write("\n--- Seeding ExportCOGS (POM→BNE) ---")
        
        # Common validity dates
        valid_from = date(2025, 1, 1)
        valid_until = date(2025, 12, 31)
        supplier = 'PX International'
        
        # COGS rates from PX rate card
        cogs_rates = [
            # Freight - weight breaks
            {
                'product_code_id': 1001,  # EXP-FRT-AIR
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'weight_breaks': [
                    {"min_kg": 0, "rate": "6.30"},
                    {"min_kg": 100, "rate": "5.90"},
                    {"min_kg": 200, "rate": "5.70"},
                    {"min_kg": 500, "rate": "5.40"},
                ],
                'min_charge': Decimal('160.00'),
            },
            # Documentation - flat fee
            {
                'product_code_id': 1010,  # EXP-DOC
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
            },
            # AWB Fee - flat fee
            {
                'product_code_id': 1011,  # EXP-AWB
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
            },
            # Terminal Fee - flat fee
            {
                'product_code_id': 1030,  # EXP-TERM
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
            },
            # Build-Up - per kg
            {
                'product_code_id': 1031,  # EXP-BUILDUP
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.15'),
                'min_charge': Decimal('30.00'),
            },
            # Security Screening - per kg + flat
            {
                'product_code_id': 1040,  # EXP-SCREEN
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.17'),
                'min_charge': Decimal('35.00'),
            },
        ]
        
        for rate_data in cogs_rates:
            obj, created = ExportCOGS.objects.update_or_create(
                product_code_id=rate_data['product_code_id'],
                origin_airport=rate_data['origin_airport'],
                destination_airport=rate_data['destination_airport'],
                valid_from=valid_from,
                defaults={
                    'currency': rate_data.get('currency', 'PGK'),
                    'rate_per_kg': rate_data.get('rate_per_kg'),
                    'rate_per_shipment': rate_data.get('rate_per_shipment'),
                    'min_charge': rate_data.get('min_charge'),
                    'max_charge': rate_data.get('max_charge'),
                    'weight_breaks': rate_data.get('weight_breaks'),
                    'supplier_name': supplier,
                    'valid_until': valid_until,
                }
            )
            pc = ProductCode.objects.get(id=rate_data['product_code_id'])
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: COGS {pc.code} POM→BNE")
    
    def _seed_export_sell_rates(self):
        """
        Seed ExportSellRate for POM→BNE corridor.
        
        Source: EFM sell rate card (what EFM charges customers)
        """
        self.stdout.write("\n--- Seeding ExportSellRate (POM→BNE) ---")
        
        # Common validity dates
        valid_from = date(2025, 1, 1)
        valid_until = date(2025, 12, 31)
        
        # Sell rates (typically higher than COGS for margin)
        sell_rates = [
            # Freight - weight breaks with margin
            {
                'product_code_id': 1001,  # EXP-FRT-AIR
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'weight_breaks': [
                    {"min_kg": 0, "rate": "7.50"},
                    {"min_kg": 100, "rate": "7.00"},
                    {"min_kg": 200, "rate": "6.80"},
                    {"min_kg": 500, "rate": "6.50"},
                ],
                'min_charge': Decimal('200.00'),
            },
            # Documentation - flat fee
            {
                'product_code_id': 1010,  # EXP-DOC
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # AWB Fee - flat fee
            {
                'product_code_id': 1011,  # EXP-AWB
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # Terminal Fee - flat fee
            {
                'product_code_id': 1030,  # EXP-TERM
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # Build-Up - per kg
            {
                'product_code_id': 1031,  # EXP-BUILDUP
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.20'),
                'min_charge': Decimal('50.00'),
            },
            # Security Screening - per kg
            {
                'product_code_id': 1040,  # EXP-SCREEN
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.20'),
                'min_charge': Decimal('45.00'),
            },
            # Clearance (SELL only - we do this in-house)
            {
                'product_code_id': 1020,  # EXP-CLEAR
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('300.00'),
            },
            # Agency Fee (SELL only)
            {
                'product_code_id': 1021,  # EXP-AGENCY
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('250.00'),
            },
            # Pickup (SELL only - we do this in-house)
            {
                'product_code_id': 1050,  # EXP-PICKUP
                'origin_airport': 'POM',
                'destination_airport': 'BNE',
                'currency': 'PGK',
                'rate_per_kg': Decimal('1.50'),
                'min_charge': Decimal('95.00'),
                'max_charge': Decimal('500.00'),
            },
        ]
        
        for rate_data in sell_rates:
            obj, created = ExportSellRate.objects.update_or_create(
                product_code_id=rate_data['product_code_id'],
                origin_airport=rate_data['origin_airport'],
                destination_airport=rate_data['destination_airport'],
                valid_from=valid_from,
                defaults={
                    'currency': rate_data.get('currency', 'PGK'),
                    'rate_per_kg': rate_data.get('rate_per_kg'),
                    'rate_per_shipment': rate_data.get('rate_per_shipment'),
                    'min_charge': rate_data.get('min_charge'),
                    'max_charge': rate_data.get('max_charge'),
                    'weight_breaks': rate_data.get('weight_breaks'),
                    'valid_until': valid_until,
                }
            )
            pc = ProductCode.objects.get(id=rate_data['product_code_id'])
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: SELL {pc.code} POM→BNE")
