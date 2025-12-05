import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")
django.setup()

from pricing_v3.charge_engine import ChargeEngine
from pricing_v3.resolvers import QuoteContext
from core.models import Policy, FxSnapshot, Currency
from quotes.models import Quote

class MockQuote:
    def __init__(self, mode, output_currency):
        self.mode = mode
        self.output_currency = output_currency

class MockContext:
    def __init__(self, mode, policy, fx_snapshot):
        self.quote = MockQuote(mode, "PGK")
        self.policy = policy
        self.fx_snapshot = fx_snapshot
        self.chargeable_weight = Decimal("100.0")
        self.mode = mode

def verify_caf_logic():
    print("Verifying CAF Logic...")
    
    # 1. Setup Mock Data
    policy = Policy(
        name="Test Policy",
        caf_import_pct=Decimal("0.20"), # 20%
        caf_export_pct=Decimal("0.30"), # 30%
        margin_pct=Decimal("0.10")
    )
    # We don't save policy to DB to avoid polluting, just use instance
    
    fx_snapshot = FxSnapshot(
        rates={"AUD": {"tt_buy": 2.0, "tt_sell": 2.0}, "PGK": {"tt_buy": 1.0, "tt_sell": 1.0}},
        fx_buffer_percent=Decimal("0.05") # 5% Buffer
    )
    
    # 2. Test Export Context
    print("\n--- Testing EXPORT Context ---")
    ctx_export = MockContext("EXPORT", policy, fx_snapshot)
    engine_export = ChargeEngine(ctx_export)
    
    # Mock SellLine for Freight
    from pricing_v3.engine_types import SellLine
    freight_line = SellLine(
        line_type='COMPONENT',
        component_code='FRT_AIR',
        description='Freight',
        cost_pgk=Decimal("100.00"),
        sell_pgk=Decimal("100.00"), # Simple 100 PGK freight
        sell_fcy=Decimal("100.00"),
        sell_currency="PGK",
        margin_percent=Decimal("0.0"),
        exchange_rate=Decimal("1.0"),
        source='TEST'
    )
    
    caf_line, caf_pgk, _ = engine_export._calculate_caf([freight_line])
    
    print(f"Freight: {freight_line.sell_pgk}")
    print(f"Calculated CAF: {caf_pgk}")
    if caf_pgk == Decimal("5.00"):
        print("RESULT: Used Default 5% (BUG CONFIRMED - Should be 30%)")
    elif caf_pgk == Decimal("30.00"):
        print("RESULT: Used Export Policy 30% (CORRECT)")
    else:
        print(f"RESULT: Used {caf_pgk}% (Unknown)")

    # 3. Test Import Context
    print("\n--- Testing IMPORT Context ---")
    ctx_import = MockContext("IMPORT", policy, fx_snapshot)
    engine_import = ChargeEngine(ctx_import)
    
    caf_line_imp, caf_pgk_imp, _ = engine_import._calculate_caf([freight_line])
    print(f"Freight: {freight_line.sell_pgk}")
    print(f"Calculated CAF: {caf_pgk_imp}")
    
    if caf_pgk_imp == Decimal("5.00"):
        print("RESULT: Used Default 5% (BUG CONFIRMED - Should be 20%)")
    elif caf_pgk_imp == Decimal("20.00"):
        print("RESULT: Used Import Policy 20% (CORRECT)")

if __name__ == "__main__":
    verify_caf_logic()
