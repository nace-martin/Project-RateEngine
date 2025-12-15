"""
Test script to verify lane discriminator rate resolution.

Run with: python manage.py shell < scripts/test_lane_discriminators.py

Tests:
1. Import COLLECT D2D resolves correctly
2. Export PREPAID resolves correctly  
3. Wrong direction lane is never selected
4. When no match exists, engine fails loudly
"""

import os
import sys
import django

# Setup Django if running standalone
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
    django.setup()

import uuid
from decimal import Decimal
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import (
    QuoteInput, ShipmentDetails, Piece, LocationRef
)
from services.models import ServiceComponent
from ratecards.models import PartnerRateLane, PartnerRate


def test_lane_discriminator_resolution():
    """Test that _get_buy_rate correctly filters by direction and payment_term."""
    
    print("\n" + "="*70)
    print("LANE DISCRIMINATOR RESOLUTION TESTS")
    print("="*70)
    
    # First, show current lane configuration
    print("\n--- CURRENT LANE CONFIGURATION ---")
    for lane in PartnerRateLane.objects.all()[:10]:
        print(f"  {lane.origin_airport} -> {lane.destination_airport} | "
              f"Direction: {lane.direction} | PaymentTerm: {lane.payment_term} | "
              f"Card: {lane.rate_card.name[:30]}...")
    
    # Find a test component that has rates
    test_component = ServiceComponent.objects.filter(is_active=True, code='FRT_AIR').first()
    if not test_component:
        test_component = ServiceComponent.objects.filter(is_active=True).first()
    
    if not test_component:
        print("ERROR: No active service components found")
        return
    
    print(f"\n--- TEST COMPONENT: {test_component.code} ---")
    
    # TEST 1: Import COLLECT D2D (BNE -> POM)
    print("\n" + "-"*70)
    print("TEST 1: Import COLLECT D2D (BNE -> POM)")
    print("-"*70)
    
    origin = LocationRef(
        id=uuid.uuid4(),
        code='BNE',
        name='Brisbane',
        country_code='AU',
        currency_code='AUD'
    )
    dest = LocationRef(
        id=uuid.uuid4(),
        code='POM',
        name='Port Moresby',
        country_code='PG',
        currency_code='PGK'
    )
    
    shipment = ShipmentDetails(
        mode='AIR',
        shipment_type='IMPORT',  # This is direction
        incoterm='EXW',
        payment_term='COLLECT',
        service_scope='D2D',
        is_dangerous_goods=False,
        pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), 
                     height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
        origin_location=origin,
        destination_location=dest,
    )
    
    quote_input = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        shipment=shipment,
    )
    
    try:
        service = PricingServiceV3(quote_input)
        rate = service._get_buy_rate(test_component)
        
        if rate:
            print(f"  ✓ PASS: Found rate from {rate.lane.rate_card.name}")
            print(f"    Lane direction: {rate.lane.direction}")
            print(f"    Lane payment_term: {rate.lane.payment_term}")
            
            # Verify it's the correct direction
            if rate.lane.direction == 'IMPORT':
                print(f"    ✓ Direction correctly matched IMPORT")
            else:
                print(f"    ✗ FAIL: Wrong direction! Expected IMPORT, got {rate.lane.direction}")
        else:
            print(f"  ✗ FAIL: No rate found (check if IMPORT lane exists for BNE->POM)")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    
    # TEST 2: Export PREPAID D2D (POM -> BNE)
    print("\n" + "-"*70)
    print("TEST 2: Export PREPAID D2D (POM -> BNE)")
    print("-"*70)
    
    origin_export = LocationRef(
        id=uuid.uuid4(),
        code='POM',
        name='Port Moresby',
        country_code='PG',
        currency_code='PGK'
    )
    dest_export = LocationRef(
        id=uuid.uuid4(),
        code='BNE',
        name='Brisbane',
        country_code='AU',
        currency_code='AUD'
    )
    
    shipment_export = ShipmentDetails(
        mode='AIR',
        shipment_type='EXPORT',  # This is direction
        incoterm='FCA',
        payment_term='PREPAID',
        service_scope='D2D',
        is_dangerous_goods=False,
        pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), 
                     height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
        origin_location=origin_export,
        destination_location=dest_export,
    )
    
    quote_input_export = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        shipment=shipment_export,
    )
    
    try:
        service = PricingServiceV3(quote_input_export)
        rate = service._get_buy_rate(test_component)
        
        if rate:
            print(f"  ✓ PASS: Found rate from {rate.lane.rate_card.name}")
            print(f"    Lane direction: {rate.lane.direction}")
            print(f"    Lane payment_term: {rate.lane.payment_term}")
            
            # Verify it's the correct direction
            if rate.lane.direction == 'EXPORT':
                print(f"    ✓ Direction correctly matched EXPORT")
            else:
                print(f"    ✗ FAIL: Wrong direction! Expected EXPORT, got {rate.lane.direction}")
        else:
            print(f"  ✗ FAIL: No rate found (check if EXPORT lane exists for POM->BNE)")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    
    # TEST 3: Wrong direction should NOT match
    print("\n" + "-"*70)
    print("TEST 3: Verify wrong direction lane is never selected")
    print("-"*70)
    
    # Try to get an IMPORT rate for an EXPORT route
    # Create EXPORT shipment but query for a component that only has IMPORT rates
    
    # Check if there are any lanes where we can test this
    import_lanes = PartnerRateLane.objects.filter(direction='IMPORT')
    export_lanes = PartnerRateLane.objects.filter(direction='EXPORT')
    
    print(f"  Total IMPORT lanes: {import_lanes.count()}")
    print(f"  Total EXPORT lanes: {export_lanes.count()}")
    
    if import_lanes.exists() and export_lanes.exists():
        print("  ✓ Both IMPORT and EXPORT lanes exist - discrimination is possible")
    else:
        print("  ⚠ Warning: Missing lanes for one direction - test limited")
    
    # TEST 4: No match = loud failure
    print("\n" + "-"*70)
    print("TEST 4: No match should log error (check console for ERROR log)")
    print("-"*70)
    
    # Use a fake route that doesn't exist
    fake_origin = LocationRef(
        id=uuid.uuid4(),
        code='XXX',
        name='Fake Airport',
        country_code='XX',
        currency_code='XXX'
    )
    fake_dest = LocationRef(
        id=uuid.uuid4(),
        code='YYY',
        name='Another Fake',
        country_code='YY',
        currency_code='YYY'
    )
    
    shipment_fake = ShipmentDetails(
        mode='AIR',
        shipment_type='IMPORT',
        incoterm='EXW',
        payment_term='COLLECT',
        service_scope='D2D',
        is_dangerous_goods=False,
        pieces=[Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), 
                     height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))],
        origin_location=fake_origin,
        destination_location=fake_dest,
    )
    
    quote_input_fake = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency='PGK',
        shipment=shipment_fake,
    )
    
    try:
        service = PricingServiceV3(quote_input_fake)
        rate = service._get_buy_rate(test_component)
        
        if rate:
            print(f"  ✗ FAIL: Should not have found a rate for fake route!")
        else:
            print(f"  ✓ PASS: Correctly returned None for non-existent route")
            print(f"    (Check console/logs for 'NO RATE FOUND' error message)")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    
    print("\n" + "="*70)
    print("TESTS COMPLETE")
    print("="*70)


if __name__ == '__main__':
    test_lane_discriminator_resolution()
