import assert from "assert";
import { recalculateSpotCharges } from "./spot-recalculation";
import { SPEChargeLine, SPEShipmentContext } from "./spot-types";

// =============================================================================
// TEST SUITE: SPOT Recalculation Engine
// =============================================================================

const mockShipment: SPEShipmentContext = {
    origin_country: "PG",
    destination_country: "AU",
    origin_code: "POM",
    destination_code: "SYD",
    commodity: "GCR",
    total_weight_kg: 500,
    pieces: 5,
};

// 1. per_kg amount * weight
function testPerKgCalculation() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT",
            description: "Air Freight",
            amount: "2.50",
            currency: "USD",
            unit: "per_kg",
            bucket: "airfreight",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const charge = result.charges[0];
    
    assert.strictEqual(charge.calculated_amount, 1250.00); // 2.50 * 500
    assert.strictEqual(charge.display_amount, "1250.00");
    assert.strictEqual(charge.amount, "2.50"); // Original amount not mutated
    assert.deepStrictEqual(result.bucketTotals.freight, { USD: 1250.00 });
    console.log("✓ testPerKgCalculation passed");
}

// 2. min_or_per_kg floor
function testMinOrPerKgFloor() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT",
            description: "Air Freight Low",
            amount: "0.10", // 0.10 * 500 = 50.00
            min_charge: "150.00", // min floor is 150.00
            currency: "USD",
            unit: "min_or_per_kg",
            bucket: "airfreight",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const charge = result.charges[0];
    
    assert.strictEqual(charge.calculated_amount, 150.00); // Floor clamped
    assert.strictEqual(charge.display_amount, "150.00");
    console.log("✓ testMinOrPerKgFloor passed");
}

// 3. percentage of freight
function testPercentageOfFreight() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT",
            description: "Air Freight",
            amount: "1000.00",
            currency: "USD",
            unit: "flat",
            bucket: "airfreight",
            source_reference: "Test",
        },
        {
            id: "2",
            code: "EXP-FSC",
            description: "Fuel Surcharge",
            amount: "0.00",
            percent: "22",
            percent_basis: "freight",
            currency: "USD",
            unit: "percentage",
            bucket: "airfreight",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const fsc = result.charges[1];
    
    assert.strictEqual(fsc.calculated_amount, 220.00); // 22% of 1000
    assert.strictEqual(fsc.display_amount, "220.00");
    assert.deepStrictEqual(result.bucketTotals.freight, { USD: 1220.00 }); // 1000 + 220
    console.log("✓ testPercentageOfFreight passed");
}

// 4. pickup FSC percentage of pickup
function testPickupFscPercentageOfPickup() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-PICKUP",
            description: "Road Pickup",
            amount: "500.00",
            currency: "USD",
            unit: "flat",
            bucket: "origin_charges",
            source_reference: "Test",
        },
        {
            id: "2",
            code: "EXP-PICKUP-FSC",
            description: "Pickup Fuel Surcharge",
            amount: "0.00",
            percent: "15",
            percent_basis: "EXP-PICKUP",
            currency: "USD",
            unit: "percentage",
            bucket: "origin_charges",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const fsc = result.charges[1];
    
    assert.strictEqual(fsc.calculated_amount, 75.00); // 15% of 500
    assert.strictEqual(fsc.display_amount, "75.00");
    console.log("✓ testPickupFscPercentageOfPickup passed");
}

// 5. min_amount floor and max_amount cap
function testMinMaxPercentageLimits() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT",
            description: "Air Freight",
            amount: "100.00",
            currency: "USD",
            unit: "flat",
            bucket: "airfreight",
            source_reference: "Test",
        },
        {
            id: "2",
            code: "EXP-FSC-LOW",
            description: "Fuel Surcharge Floor",
            amount: "0.00",
            percent: "22", // 22% of 100 = 22.00
            min_amount: "50.00", // min floor is 50.00
            percent_basis: "freight",
            currency: "USD",
            unit: "percentage",
            bucket: "airfreight",
            source_reference: "Test",
        },
        {
            id: "3",
            code: "EXP-FSC-HIGH",
            description: "Fuel Surcharge Cap",
            amount: "0.00",
            percent: "22", // 22% of 100 = 22.00
            max_amount: "15.00", // max cap is 15.00
            percent_basis: "freight",
            currency: "USD",
            unit: "percentage",
            bucket: "airfreight",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const fscLow = result.charges[1];
    const fscHigh = result.charges[2];
    
    assert.strictEqual(fscLow.calculated_amount, 50.00); // Min floor applied
    assert.strictEqual(fscHigh.calculated_amount, 15.00); // Max cap applied
    console.log("✓ testMinMaxPercentageLimits passed");
}

// 6. Excluded charges ignored
function testExcludedChargesIgnored() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT",
            description: "Air Freight",
            amount: "1000.00",
            currency: "USD",
            unit: "flat",
            bucket: "airfreight",
            source_reference: "Test",
        },
        {
            id: "2",
            code: "EXP-DOC",
            description: "Documentation Fee",
            amount: "150.00",
            currency: "USD",
            unit: "flat",
            bucket: "origin_charges",
            exclude_from_totals: true, // excluded
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const freight = result.charges[0];
    const doc = result.charges[1];
    
    assert.strictEqual(freight.calculated_amount, 1000.00);
    assert.strictEqual(doc.calculated_amount, 0); // Excluded is 0
    assert.deepStrictEqual(result.bucketTotals.origin_charges || {}, {}); // Origin bucket has no totals
    console.log("✓ testExcludedChargesIgnored passed");
}

// 7. Unacknowledged conditional charges ignored
function testUnacknowledgedConditionalCharges() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT",
            description: "Air Freight",
            amount: "1000.00",
            currency: "USD",
            unit: "flat",
            bucket: "airfreight",
            source_reference: "Test",
        },
        {
            id: "2",
            code: "EXP-CONDITIONAL",
            description: "Conditional Charge",
            amount: "200.00",
            currency: "USD",
            unit: "flat",
            bucket: "origin_charges",
            conditional: true,
            conditional_acknowledged: false, // not acknowledged
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const cond = result.charges[1];
    
    assert.strictEqual(cond.calculated_amount, 0);
    assert.deepStrictEqual(result.bucketTotals.origin_charges || {}, {});
    console.log("✓ testUnacknowledgedConditionalCharges passed");
}

// 8. Mixed currency totals separated
function testMixedCurrencyTotals() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FREIGHT-USD",
            description: "Air Freight USD",
            amount: "1000.00",
            currency: "USD",
            unit: "flat",
            bucket: "airfreight",
            source_reference: "Test",
        },
        {
            id: "2",
            code: "EXP-FREIGHT-PGK",
            description: "Air Freight PGK",
            amount: "3000.00",
            currency: "PGK",
            unit: "flat",
            bucket: "airfreight",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    
    assert.deepStrictEqual(result.bucketTotals.freight, { USD: 1000.00, PGK: 3000.00 });
    console.log("✓ testMixedCurrencyTotals passed");
}

// 9. Percentage basis missing returns warning
function testMissingPercentageBasis() {
    const visible: SPEChargeLine[] = [
        {
            id: "1",
            code: "EXP-FSC",
            description: "Fuel Surcharge",
            amount: "0.00",
            percent: "22",
            percent_basis: "", // Missing
            currency: "USD",
            unit: "percentage",
            bucket: "airfreight",
            source_reference: "Test",
        }
    ];
    
    const result = recalculateSpotCharges(visible, [], mockShipment);
    const fsc = result.charges[0];
    
    assert.strictEqual(fsc.calculated_amount, 0);
    assert.ok(fsc.warnings && fsc.warnings.includes("Missing applies-to basis"));
    console.log("✓ testMissingPercentageBasis passed");
}

// RUN ALL TESTS
try {
    testPerKgCalculation();
    testMinOrPerKgFloor();
    testPercentageOfFreight();
    testPickupFscPercentageOfPickup();
    testMinMaxPercentageLimits();
    testExcludedChargesIgnored();
    testUnacknowledgedConditionalCharges();
    testMixedCurrencyTotals();
    testMissingPercentageBasis();
    console.log("\n========================================================");
    console.log("ALL SPOT RECALCULATION ENGINE TESTS PASSED SUCCESSFULLY!");
    console.log("========================================================\n");
} catch (error) {
    console.error("Test execution failed:", error);
    process.exit(1);
}
