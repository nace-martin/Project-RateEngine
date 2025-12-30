"""
Quick test script for ai_intake_service with a real-world agent email.
Test 2: PREPAID EXPORT D2D - POM,PG to SIN,SG
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.ai_intake_service import parse_rate_quote_text
import json

# Example 2: Singapore agent (POM to SIN - PREPAID Export D2D)
EXAMPLE_EMAIL = """
Dear Nason

You may use below table, airline mawb to consign to Everprime to avoid fee in yellow highlight: 
					
	IMPORT AIR CHARGES				
					
Description		Amount (SGD $)		
Terminal Fee		35.00	min or 0.25 per KGS	
Agent Clearance Fee	35.00	min or 0.25 per KGS	
Clear from agent warehouse	35.00	min or 0.25 per KGS	(If Applicable)
Airline Doc Fee		15.00	per AWB		
Cargo Terminal Collection Fee	10.00	min or 0.04 per KGS	
Permit		50.00	per set (max 5 lines, thereafter @ sgd 2 / line)
Transport		105.00	min or 0.12 per KGS	
Fuel Surcharge		5.00	min or 0.02 per KGS	
CMD Fee		20.00	per shpt		
Handling		50.00	per shpt		
DNATA Imp Processing Fee	10.00	per shpt	(If Applicable)
Labour		75.00	per man		
Tailgate Truck		135.00	per trip (if applicable) or 0.12 per KGS
Service Fee (if via LH/AF/KLM)	12.00	per shpt	(If Applicable)
Import GST to be 9% of Commercial Invoice			
					
					
					
Delivery time: 0900hrs to 1730hrs (Mon to Fri), 0900hrs to 1300hrs (Sat)
After office surcharge - SGD 80.00 for First 2 hours (subsequent S$50 per hours)
Saturday surcharge after 1300 hrs - SGD90.00 for First 2 hours (subsequent S$50 per hours)
Sunday / Public Holiday surcharges - SGD 180.00 for First 2 hours (subsequent S$90 per hours)
Late minutes cancellation of job within the same day, a cancellation fee of SGD 160.00 will be charged accordingly
Midnight surcharge (between 12 midnight to 6 am - Above charges X2 plus SGD100.00 per job

Above quote in sgd, pls use exchange rate usd 1 = sgd 1.28

Thanks and Best Regards,
Fenny Khng
 
 Everprime Shipping Pte Ltd
       420 North Bridge Road 
       #02-32 North Bridge Centre 
       Singapore 188727
       Tel: 6297 6388 Fax: 6297 5108 
"""

# Context for this quote request - Export from POM to SIN
CONTEXT = {
    "origin": "Port Moresby, Papua New Guinea",
    "origin_code": "POM",
    "destination": "Singapore",
    "destination_code": "SIN",
    "weight": "100",  # Example weight
    "shipment_type": "EXPORT",
    "incoterm": "D2D",
    "payment_term": "PREPAID",
    "missing_components": ["DESTINATION_DELIVERY", "DESTINATION_HANDLING", "DESTINATION_CLEARANCE", "DESTINATION_DOCS"]
}

def main():
    print("=" * 70)
    print("AI INTAKE SERVICE TEST - EXAMPLE 2")
    print("=" * 70)
    print(f"\nScenario: PREPAID EXPORT D2D - POM,PG to SIN,SG")
    print(f"Testing with agent email from Singapore (Everprime)...")
    print(f"This email has complex 'min or per kg' pricing structures")
    print("-" * 70)
    
    # Call the AI intake service
    result = parse_rate_quote_text(
        text=EXAMPLE_EMAIL,
        source_type="EMAIL",
        context=CONTEXT
    )
    
    print(f"\n[OK] SUCCESS: {result.success}")
    
    if result.error:
        print(f"[ERROR] {result.error}")
        return
    
    print(f"\n[ANALYSIS]:")
    print("-" * 50)
    # Safely encode the analysis text for Windows console
    analysis_safe = result.analysis_text.encode('ascii', 'replace').decode('ascii') if result.analysis_text else ""
    print(analysis_safe)
    
    print(f"\n[EXTRACTED CHARGE LINES] ({len(result.lines)} found):")
    print("-" * 50)
    
    for i, line in enumerate(result.lines, 1):
        print(f"\n  [{i}] {line.description}")
        print(f"      Bucket: {line.bucket}")
        print(f"      Unit Basis: {line.unit_basis}")
        if line.amount:
            print(f"      Amount: {line.amount} {line.currency}")
        if line.rate_per_unit:
            print(f"      Rate Per Unit: {line.rate_per_unit} {line.currency}/kg")
        if line.minimum:
            print(f"      Minimum: {line.minimum} {line.currency}")
        if line.maximum:
            print(f"      Maximum: {line.maximum}")
        if line.percentage:
            print(f"      Percentage: {line.percentage}%")
        if line.percent_applies_to:
            print(f"      Applies To: {line.percent_applies_to}")
    
    if result.warnings:
        print(f"\n[WARNINGS]:")
        for w in result.warnings:
            print(f"  - {w}")
    
    print(f"\n[METADATA]:")
    print(f"  - Model Used: {result.model_used}")
    print(f"  - Source Type: {result.source_type}")
    print(f"  - Raw Text Length: {result.raw_text_length}")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
