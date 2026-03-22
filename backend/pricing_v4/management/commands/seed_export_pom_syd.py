# backend/pricing_v4/management/commands/seed_export_pom_bne.py
"""
Seed ProductCodes and rates for the first corridor: Export Air D2A Prepaid POM->BNE

Rule 8: ProductCode must exist before any rate row
Rule 9: One corridor must work end-to-end before expanding

AMENDMENTS:
- Security Screening: per-kg + flat fee (additive, no minimum)
- FSC on Pickup: 10% of Pickup/Collection charge
- Carrier vs Agent distinction enforced
"""

from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import Carrier, Agent, ProductCode, ExportCOGS
from pricing_v4.management.commands._sell_seed_utils import seed_export_sell_rate


class Command(BaseCommand):
    help = 'Seeds Export rates for POM->SYD corridor'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=date.today().year,
            help='Seed rates for the given year (default: current year).',
        )

    def handle(self, *args, **options):
        self.year = options['year']
        self.stdout.write("=" * 60)
        self.stdout.write(f"Seeding Export rates for POM->SYD corridor ({self.year})")
        self.stdout.write("=" * 60)
        
        with transaction.atomic():
            self._seed_carriers()
            self._seed_agents()
            self._seed_product_codes()
            self._seed_export_cogs()
            self._seed_export_sell_rates()
        
        self.stdout.write(self.style.SUCCESS("\nCorridor seeding complete!"))
    
    def _seed_carriers(self):
        """Seed carriers (airlines/shipping lines for freight COGS)."""
        self.stdout.write("\n--- Seeding Carriers ---")
        
        carriers = [
            {'code': 'PX', 'name': 'Air Niugini', 'carrier_type': 'AIRLINE'},
            {'code': 'QF', 'name': 'Qantas', 'carrier_type': 'AIRLINE'},
            {'code': 'CZ', 'name': 'China Southern', 'carrier_type': 'AIRLINE'},
        ]
        
        for data in carriers:
            obj, created = Carrier.objects.update_or_create(
                code=data['code'],
                defaults={'name': data['name'], 'carrier_type': data['carrier_type']}
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {obj}")
    
    def _seed_agents(self):
        """Seed agents (forwarders for origin/destination services).
        
        Note: For Exports, PX handles all services (freight + ground).
        Agents are used for destination services or when third parties are involved.
        """
        self.stdout.write("\n--- Seeding Agents ---")
        
        agents = [
            {'code': 'EFM-PG', 'name': 'EFM PNG (Internal)', 'country_code': 'PG', 'agent_type': 'ORIGIN'},
            {'code': 'EFM-AU', 'name': 'EFM Australia', 'country_code': 'AU', 'agent_type': 'DESTINATION'},
            # Note: PX is a carrier, not an agent. For Exports, all PX services use carrier=PX.
        ]
        
        for data in agents:
            obj, created = Agent.objects.update_or_create(
                code=data['code'],
                defaults={
                    'name': data['name'],
                    'country_code': data['country_code'],
                    'agent_type': data['agent_type'],
                }
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: {obj}")
    
    def _seed_product_codes(self):
        """
        Seed ProductCodes for Export domain.
        
        ID Range: 1xxx
        Rule 8: ProductCodes must exist FIRST.
        """
        self.stdout.write("\n--- Seeding ProductCodes (1xxx Export) ---")
        
        # First, seed the base pickup code
        pickup_code = {
            'id': 1050,
            'code': 'EXP-PICKUP',
            'description': 'Export Pickup/Collection',
            'category': ProductCode.CATEGORY_CARTAGE,
            'is_gst_applicable': False,
            'gst_rate': Decimal('0.00'),
            'gl_revenue_code': '4500',
            'gl_cost_code': '5500',
            'default_unit': ProductCode.UNIT_KG,
            'percent_of_product_code': None,
        }
        
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
                  'description': 'Export Terminal Fee',
                  'category': ProductCode.CATEGORY_HANDLING,
                  'is_gst_applicable': False,
                  'gst_rate': Decimal('0.00'),
                  'gl_revenue_code': '4400',
                  'gl_cost_code': '5400',
                  'default_unit': ProductCode.UNIT_SHIPMENT,
              },
              {
                  'id': 1032,
                  'code': 'EXP-HANDLE',
                  'description': 'Export Handling Fee',
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
                'default_unit': ProductCode.UNIT_KG,  # per-kg + flat fee
            },
            # 1050-1059: Cartage (Pickup) - defined first, insert here
            pickup_code,
            # 1070-1079: Dangerous Goods
            {
                'id': 1070,
                'code': 'EXP-DG',
                'description': 'Export DG Acceptance',
                'category': ProductCode.CATEGORY_HANDLING,
                'is_gst_applicable': False,
                'gst_rate': Decimal('0.00'),
                'gl_revenue_code': '4400',
                'gl_cost_code': '5400',
                'default_unit': ProductCode.UNIT_SHIPMENT,
            },
        ]
        
        # Create pickup first (needed for FSC reference)
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
        
        # Now create FSC with reference to Pickup
        pickup_pc = ProductCode.objects.get(id=1050)
        fsc_code = {
            'id': 1060,
            'code': 'EXP-FSC-PICKUP',
            'description': 'Export Fuel Surcharge on Pickup',
            'category': ProductCode.CATEGORY_SURCHARGE,
            'is_gst_applicable': False,
            'gst_rate': Decimal('0.00'),
            'gl_revenue_code': '4500',
            'gl_cost_code': '5500',
            'default_unit': ProductCode.UNIT_PERCENT,
            'percent_of_product_code': pickup_pc,
        }
        
        obj, created = ProductCode.objects.update_or_create(
            id=fsc_code['id'],
            defaults={
                'code': fsc_code['code'],
                'description': fsc_code['description'],
                'domain': ProductCode.DOMAIN_EXPORT,
                'category': fsc_code['category'],
                'is_gst_applicable': fsc_code['is_gst_applicable'],
                'gst_rate': fsc_code['gst_rate'],
                'gl_revenue_code': fsc_code['gl_revenue_code'],
                'gl_cost_code': fsc_code['gl_cost_code'],
                'default_unit': fsc_code['default_unit'],
                'percent_of_product_code': fsc_code['percent_of_product_code'],
            }
        )
        status = "Created" if created else "Updated"
        self.stdout.write(f"  {status}: {obj.id} - {obj.code} (% of {pickup_pc.code})")
    
    def _seed_export_cogs(self):
        """
        Seed ExportCOGS for POM->BNE corridor.
        
        Source: PX rate card (what EFM pays)
        
        For Exports, PX (the carrier) handles ALL services:
        - Freight linehaul
        - Ground handling (documentation, terminal, build-up, screening)
        
        All COGS use carrier=PX.
        """
        self.stdout.write("\n--- Seeding ExportCOGS (POM->SYD) ---")
        
        # Get carrier - PX handles all Export services
        carrier_px = Carrier.objects.get(code='PX')
        
        # Common validity dates
        valid_from = date(self.year, 1, 1)
        valid_until = date(self.year, 12, 31)
        
        # COGS rates from PX rate card - all services via carrier PX
        cogs_rates = [
            # Freight - weight breaks
            {
                'product_code_id': 1001,  # EXP-FRT-AIR
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'weight_breaks': [
                    {"min_kg": 0, "rate": "8.00"},
                    {"min_kg": 100, "rate": "7.50"},
                    {"min_kg": 200, "rate": "7.10"},
                    {"min_kg": 500, "rate": "6.80"},
                ],
                'min_charge': Decimal('160.00'),
                'is_additive': False,
            },
            # Documentation - flat fee (PX handles this for Exports)
            {
                'product_code_id': 1010,  # EXP-DOC
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
                'is_additive': False,
            },
            # AWB Fee - flat fee
            {
                'product_code_id': 1011,  # EXP-AWB
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
                'is_additive': False,
            },
            # Terminal Fee - flat fee
            {
                'product_code_id': 1030,  # EXP-TERM
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
                'is_additive': False,
            },
            # Handling Fee - flat fee
            {
                'product_code_id': 1032,  # EXP-HANDLE
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_shipment': Decimal('35.00'),
                'is_additive': False,
            },
            # Build-Up - per kg
            {
                'product_code_id': 1031,  # EXP-BUILDUP
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.15'),
                'min_charge': Decimal('30.00'),
                'is_additive': False,
            },
            # Security Screening - per kg + flat fee (ADDITIVE, no min)
            # K0.17/kg + K35 flat
            {
                'product_code_id': 1040,  # EXP-SCREEN
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.17'),
                'rate_per_shipment': Decimal('35.00'),
                'is_additive': True,  # KEY: per-kg + flat fee combined
                'min_charge': None,   # No minimum - additive calculation
            },
            # DG Acceptance - flat fee (for dangerous goods shipments)
            {
                'product_code_id': 1070,  # EXP-DG
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'carrier': carrier_px,
                'agent': None,
                'currency': 'PGK',
                'rate_per_shipment': Decimal('100.00'),
                'is_additive': False,
            },
        ]
        
        for rate_data in cogs_rates:
            obj, created = ExportCOGS.objects.update_or_create(
                product_code_id=rate_data['product_code_id'],
                origin_airport=rate_data['origin_airport'],
                destination_airport=rate_data['destination_airport'],
                carrier=rate_data.get('carrier'),
                agent=rate_data.get('agent'),
                valid_from=valid_from,
                defaults={
                    'currency': rate_data.get('currency', 'PGK'),
                    'rate_per_kg': rate_data.get('rate_per_kg'),
                    'rate_per_shipment': rate_data.get('rate_per_shipment'),
                    'min_charge': rate_data.get('min_charge'),
                    'max_charge': rate_data.get('max_charge'),
                    'weight_breaks': rate_data.get('weight_breaks'),
                    'is_additive': rate_data.get('is_additive', False),
                    'valid_until': valid_until,
                }
            )
            pc = ProductCode.objects.get(id=rate_data['product_code_id'])
            counterparty = rate_data.get('carrier') or rate_data.get('agent')
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status}: COGS {pc.code} POM->SYD ({counterparty})")
    
    def _seed_export_sell_rates(self):
        """
        Seed ExportSellRate for POM->BNE corridor.
        
        Source: EFM sell rate card (what EFM charges customers)
        """
        self.stdout.write("\n--- Seeding ExportSellRate (POM->SYD) ---")
        
        # Common validity dates
        valid_from = date(self.year, 1, 1)
        valid_until = date(self.year, 12, 31)
        
        # Sell rates from actual rate card
        sell_rates = [
            # Freight - weight breaks from EXPORT SELL PREPAID D2A rate card
            {
                'product_code_id': 1001,  # EXP-FRT-AIR
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'weight_breaks': [
                    {"min_kg": 0, "rate": "10.00"},    # <=99kg
                    {"min_kg": 100, "rate": "9.40"},  # +100kg
                    {"min_kg": 200, "rate": "8.90"},  # +200kg
                    {"min_kg": 500, "rate": "8.50"},  # +500kg
                ],
                'min_charge': Decimal('200.00'),
            },
            # Documentation - flat fee
            {
                'product_code_id': 1010,  # EXP-DOC
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # AWB Fee - flat fee
            {
                'product_code_id': 1011,  # EXP-AWB
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # Terminal Fee - flat fee
            {
                'product_code_id': 1030,  # EXP-TERM
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # Handling Fee - flat fee
            {
                'product_code_id': 1032,  # EXP-HANDLE
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('50.00'),
            },
            # Build-Up - per kg
            {
                'product_code_id': 1031,  # EXP-BUILDUP
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.20'),
                'min_charge': Decimal('50.00'),
            },
            # Security Screening - per kg + flat fee (ADDITIVE)
            # K0.20/kg + K45 flat (from rate card)
            {
                'product_code_id': 1040,  # EXP-SCREEN
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_kg': Decimal('0.20'),
                'rate_per_shipment': Decimal('45.00'),
                'is_additive': True,  # per-kg + flat combined
            },
            # Clearance (SELL only - we do this in-house)
            {
                'product_code_id': 1020,  # EXP-CLEAR
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('300.00'),
            },
            # Agency Fee (SELL only)
            {
                'product_code_id': 1021,  # EXP-AGENCY
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('250.00'),
            },
            # Pickup (SELL only - we do this in-house)
            {
                'product_code_id': 1050,  # EXP-PICKUP
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_kg': Decimal('1.50'),
                'min_charge': Decimal('95.00'),
                'max_charge': Decimal('500.00'),
            },
            # FSC on Pickup - 10% of Pickup charge
            {
                'product_code_id': 1060,  # EXP-FSC-PICKUP
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'percent_rate': Decimal('10.00'),  # 10%
            },
            # DG Acceptance - flat fee (for dangerous goods shipments)
            {
                'product_code_id': 1070,  # EXP-DG
                'origin_airport': 'POM',
                'destination_airport': 'SYD',
                'currency': 'PGK',
                'rate_per_shipment': Decimal('250.00'),
            },
        ]
        
        percent_of_pickup = ProductCode.objects.get(id=1050)

        for rate_data in sell_rates:
            pc = ProductCode.objects.get(id=rate_data['product_code_id'])
            result = seed_export_sell_rate(
                product_code=pc,
                origin_airport=rate_data['origin_airport'],
                destination_airport=rate_data['destination_airport'],
                currency=rate_data.get('currency', 'PGK'),
                valid_from=valid_from,
                valid_until=valid_until,
                rate_per_kg=rate_data.get('rate_per_kg'),
                rate_per_shipment=rate_data.get('rate_per_shipment'),
                min_charge=rate_data.get('min_charge'),
                max_charge=rate_data.get('max_charge'),
                weight_breaks=rate_data.get('weight_breaks'),
                percent_rate=rate_data.get('percent_rate'),
                is_additive=rate_data.get('is_additive', False),
                payment_term='PREPAID',
                percent_of_product_code=percent_of_pickup if pc.id == 1060 else None,
            )
            status = "Created" if result.created else "Updated"
            self.stdout.write(f"  {status}: {result.table_name} {pc.code} POM->SYD")
