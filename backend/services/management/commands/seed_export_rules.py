
from django.core.management.base import BaseCommand
from django.db import transaction
from services.models import ServiceRule, ServiceComponent, ServiceRuleComponent

class Command(BaseCommand):
    help = 'Seeds Service Rules for Export and Agent Workflows'

    def handle(self, *args, **options):
        self.stdout.write("Seeding Export Service Rules...")
        
        with transaction.atomic():
            self._seed_rules()
            
        self.stdout.write(self.style.SUCCESS("Successfully seeded Export Service Rules"))

    def _seed_rules(self):
        # 1. Prepaid D2D Export (DAP)
        # Scope: Origin + Freight + Destination
        # Currency: PGK (Default)
        dap_export, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='DAP',
            payment_term='PREPAID',
            service_scope='D2D',
            defaults={
                "description": "Prepaid D2D Export (Standard)",
                "output_currency_type": "ORIGIN", # PGK
                "is_active": True
            }
        )
        
        # Components for DAP Export
        dap_components = [
            # Origin
            'PICKUP_SELL', 'PICKUP_FUEL', 'DOC_EXP_SELL', 'AWB_FEE_SELL', 'SECURITY_SELL', 'AGENCY_EXP_SELL', 'CLEARANCE_SELL', 'CUSTOMS_ENTRY',
            # Freight
            'FRT_AIR_EXP', 'FRT_AIR_FUEL', # Need to ensure FRT_AIR_FUEL exists and links to FRT_AIR_EXP? Or just use generic?
            # Destination (Standard components, will look for Buy Rates)
            'DST-DELIV-STD', 'DST-DELIV-FUEL', 'DST-CLEAR-CUS', 'DST-AGENCY-IMP', 'DST-DOC-IMP', 'DST-HANDL-STD', 'DST-TERM-INTL'
        ]
        
        self._link_components(dap_export, dap_components)

        # 1b. Prepaid D2D Export (EXW) - Same components as DAP
        exw_d2d_export, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='EXW',
            payment_term='PREPAID',
            service_scope='D2D',
            defaults={
                "description": "Prepaid D2D Export (EXW)",
                "output_currency_type": "PGK",
                "is_active": True
            }
        )
        self._link_components(exw_d2d_export, dap_components)

        # 2. Collect D2A Export (EXW)
        # Scope: Origin Only (usually) or Origin + Freight
        # Currency: FCY (AUD/USD) -> We'll set to DESTINATION or USD/AUD? 
        # User said "Quote in their currency — typically USD or AUD".
        # We'll set output_currency_type='DESTINATION' (matches agent's location) or allow override.
        exw_export, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='EXW',
            payment_term='COLLECT',
            service_scope='D2A', # Or D2D if agent manages destination? Usually D2A means we deliver to airport.
            # Actually, EXW means we just make it available at Origin.
            # But "Collect D2A Export" implies we might do the origin leg?
            # User said: "They only need our origin uplift charges (Air Freight + Origin Fees)."
            # So it's D2A (Door to Airport).
            defaults={
                "description": "Collect D2A Export (Agent Request)",
                "output_currency_type": "DESTINATION", # Quote in Agent's currency
                "is_active": True
            }
        )
        
        exw_components = [
            'PICKUP_SELL', 'PICKUP_FUEL', 'DOC_EXP_SELL', 'AWB_FEE_SELL', 'SECURITY_SELL', 'AGENCY_EXP_SELL', 'CLEARANCE_SELL', 'CUSTOMS_ENTRY',
            'FRT_AIR_EXP', 'FRT_AIR_FUEL'
        ]
        self._link_components(exw_export, exw_components)

        # 2b. Prepaid D2A Export (EXW)
        # Same components as Collect D2A (Origin + Freight), but Prepaid
        exw_d2a_prepaid, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='EXW',
            payment_term='PREPAID',
            service_scope='D2A',
            defaults={
                "description": "Prepaid D2A Export (EXW)",
                "output_currency_type": "PGK",
                "is_active": True
            }
        )
        self._link_components(exw_d2a_prepaid, exw_components)

        # 2c. Prepaid D2A Export (FCA) - Standard Commercial Export
        fca_d2a_prepaid, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='FCA',
            payment_term='PREPAID',
            service_scope='D2A',
            defaults={
                "description": "Prepaid D2A Export (FCA Standard)",
                "output_currency_type": "PGK",
                "is_active": True
            }
        )
        # FCA Components: Freight + Surcharges + Export Fees (Clearance/Agency/Doc)
        # Note: Using Component Codes directly
        fca_components = [
            'FRT_AIR_EXP',      # Freight
            'SEC_EXP_MXC',      # Security (Composite)
            'DOC_EXP_AWB',      # AWB Fee
            'DOC_EXP_BIC',      # Doc Fee
            'HND_EXP_BSC',      # Terminal Fee
            'HND_EXP_BPC',      # Build Up Fee
            'CLEAR_EXP',        # Export Clearance
            'AGENCY_EXP',       # Export Agency
            'PICKUP_EXP',       # Pickup (Optional but included in calculation if payload has it?)
            'FUEL_SURCHARGE_EXP' # Fuel
        ]
        self._link_components(fca_d2a_prepaid, fca_components)

        # 3. Prepaid Import A2D (DAP - Agent)
        # Scope: Destination Only
        # Currency: FCY
        dap_import_agent, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='IMPORT',
            incoterm='DAP',
            payment_term='PREPAID', # Agent pays us prepaid? Or we bill them?
            # User said "Prepaid Import A2D... They only want our destination clearance + delivery charges."
            # Usually this is "DAP" but we are the destination agent.
            service_scope='A2D',
            defaults={
                "description": "Prepaid Import A2D (Agent Request)",
                "output_currency_type": "ORIGIN", # We quote in OUR currency? No, "We must return these charges in their foreign currency".
                # So if Agent is in BNE (AUD), and we are in POM (PGK), we quote in AUD?
                # No, usually we quote in OUR local currency (PGK) and they convert?
                # User said: "We must return these charges in their foreign currency (usually USD or AUD)".
                # So output_currency_type should be 'USD' or 'AUD' or 'DESTINATION' (Agent's currency).
                # Since Agent is the "Customer" here, and they are overseas, 'DESTINATION' might imply POM if it's Import?
                # Import: Origin (Overseas) -> Destination (POM).
                # If we quote in Agent's currency (Origin), then it's 'ORIGIN'.
                # Wait, for Import, Origin is Overseas.
                # So 'ORIGIN' = Match Origin Currency (Agent's Currency).
                # UPDATE: User confirmed AU origin → AUD, else → USD
                "output_currency_type": "ORIGIN_AU_USD", 
                "is_active": True
            }
        )
        
        import_components = [
            'DST-DELIV-STD', 'DST-DELIV-FUEL', 'DST-CLEAR-CUS', 'DST-AGENCY-IMP', 'DST-DOC-IMP', 'DST-HANDL-STD', 'DST-TERM-INTL'
        ]
        self._link_components(dap_import_agent, import_components)

        # =====================================================================
        # CPT - CARRIAGE PAID TO (Seller pays freight to destination terminal)
        # =====================================================================
        # Per Incoterms 2020: Seller covers Origin + Export + Freight + Dest Terminal
        # Buyer covers: Import customs + Inland delivery
        
        # CPT Export D2A PREPAID
        cpt_d2a_export, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='CPT',
            payment_term='PREPAID',
            service_scope='D2A',
            defaults={
                "description": "CPT Export D2A - Carriage Paid To (Airport)",
                "output_currency_type": "PGK",
                "is_active": True
            }
        )
        # CPT includes: Origin + Freight + Destination Terminal Handling
        cpt_d2a_components = [
            # Origin
            'PICKUP_EXP', 'FUEL_SURCHARGE_EXP',
            # Export Terminal
            'DOC_EXP_AWB', 'DOC_EXP_BIC', 'SEC_EXP_MXC', 'HND_EXP_BSC', 'HND_EXP_BPC',
            'CLEAR_EXP', 'AGENCY_EXP',
            # Freight
            'FRT_AIR_EXP',
            # Destination Terminal (seller pays terminal handling)
            'DST-HANDL-STD', 'DST-TERM-INTL'
        ]
        self._link_components(cpt_d2a_export, cpt_d2a_components)

        # CPT Export D2D PREPAID (includes inland delivery at destination)
        cpt_d2d_export, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='CPT',
            payment_term='PREPAID',
            service_scope='D2D',
            defaults={
                "description": "CPT Export D2D - Carriage Paid To (Door)",
                "output_currency_type": "PGK",
                "is_active": True
            }
        )
        # CPT D2D: Same as D2A + Destination Delivery (but NOT import customs)
        cpt_d2d_components = cpt_d2a_components + ['DST-DELIV-STD', 'DST-DELIV-FUEL']
        self._link_components(cpt_d2d_export, cpt_d2d_components)

        # =====================================================================
        # DDP - DELIVERED DUTY PAID (Seller pays EVERYTHING including duties)
        # =====================================================================
        # Per Incoterms 2020: Seller covers ALL charges including import duties/taxes
        # Note: Import Duty/Tax are SPOT components (user inputs from customs broker)
        
        ddp_d2d_export, _ = ServiceRule.objects.update_or_create(
            mode='AIR',
            direction='EXPORT',
            incoterm='DDP',
            payment_term='PREPAID',
            service_scope='D2D',
            defaults={
                "description": "DDP Export D2D - Delivered Duty Paid",
                "output_currency_type": "PGK",
                "is_active": True
            }
        )
        # DDP includes: ALL charges
        ddp_components = [
            # Origin
            'PICKUP_EXP', 'FUEL_SURCHARGE_EXP',
            # Export Terminal
            'DOC_EXP_AWB', 'DOC_EXP_BIC', 'SEC_EXP_MXC', 'HND_EXP_BSC', 'HND_EXP_BPC',
            'CLEAR_EXP', 'AGENCY_EXP',
            # Freight
            'FRT_AIR_EXP',
            # Destination (ALL)
            'DST-HANDL-STD', 'DST-TERM-INTL',
            'DST-CLEAR-CUS', 'DST-DOC-IMP', 'DST-AGENCY-IMP',
            'DST-DELIV-STD', 'DST-DELIV-FUEL',
            # Note: IMPORT_DUTY and IMPORT_TAX are added via SPOT charges by user
        ]
        self._link_components(ddp_d2d_export, ddp_components)

    def _link_components(self, rule, component_codes):
        # Clear existing
        rule.rule_components.all().delete()
        
        for idx, code in enumerate(component_codes):
            # Handle ServiceCode vs ServiceComponent code
            # The list above uses Component codes (mostly).
            # Some might be ServiceCodes (e.g. DST-DELIV-STD).
            # We need to find the Component.
            
            # Try to find component by code
            comp = ServiceComponent.objects.filter(code=code).first()
            if not comp:
                # Try to find by ServiceCode
                # This assumes we have a component linked to this ServiceCode
                # For now, let's assume the codes in the list ARE Component codes or we created them.
                # The DST- codes in seed_service_codes.py are ServiceCodes.
                # We need to check if Components exist for them.
                # Usually seed_service_codes.py creates ServiceCodes, but not Components?
                # No, seed_service_codes.py creates ServiceCodes.
                # We need Components.
                # Let's assume standard components exist or create them if missing.
                
                # Create placeholder if missing (for DST items)
                if code.startswith('DST-'):
                    comp, _ = ServiceComponent.objects.get_or_create(
                        code=code, # Using ServiceCode as Component Code for simplicity
                        defaults={
                            "description": code,
                            "leg": "DESTINATION",
                            "mode": "AIR",
                            "cost_type": "COGS", # Buy Rate (we pay 3rd party)
                            "cost_source": "BASE_COST", # Or PARTNER_RATECARD
                        }
                    )
                else:
                    self.stdout.write(self.style.WARNING(f"Component {code} not found. Skipping."))
                    continue
            
            ServiceRuleComponent.objects.create(
                service_rule=rule,
                service_component=comp,
                sequence=idx + 1,
                is_mandatory=True
            )
            self.stdout.write(f"Linked {code} to {rule}")

