
from decimal import Decimal

def run():
    print("--- Simulating Weight Break Logic ---")
    
    chargeable_weight = Decimal("166.6666666666666667") # 166.67
    print(f"Chargeable Weight: {chargeable_weight}")
    
    breaks = [
      { "min_kg": 0, "rate_per_kg": 7.9 },
      { "min_kg": 100, "rate_per_kg": 7.4 },
      { "min_kg": 200, "rate_per_kg": 7.15 },
      { "min_kg": 500, "rate_per_kg": 6.75 }
    ]
    
    sorted_breaks = sorted(
        breaks,
        key=lambda x: Decimal(str(x.get("min_kg", "0"))),
        reverse=True,
    )
    
    print("Sorted Breaks:")
    for b in sorted_breaks:
        print(b)
        
    selected_rate = None
    for tier in sorted_breaks:
        min_kg_val = tier.get("min_kg", "0")
        min_kg_dec = Decimal(str(min_kg_val))
        print(f"Checking {chargeable_weight} >= {min_kg_dec} ({type(min_kg_val)})?")
        
        if chargeable_weight >= min_kg_dec:
            selected_rate = Decimal(str(tier.get("rate_per_kg")))
            print(f"MATCH! Rate: {selected_rate}")
            break
            
    if selected_rate:
        cost = chargeable_weight * selected_rate
        print(f"Cost: {cost}")
    else:
         print("No Valid Rate Found")

if __name__ == "__main__":
    run()
