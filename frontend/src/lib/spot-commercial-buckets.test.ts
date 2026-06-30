/**
 * Tests for commercial bucket scoping helpers.
 *
 * Verifies:
 * 1. Per-charge dropdown isolation (customs/transport don't leak to other rows)
 * 2. Empty non-core sections are suppressed
 * 3. AWB/document charges infer to Origin Charges
 * 4. Core vs sub-bucket visibility rules
 */

import {
    inferCommercialBucket,
    getVisibleCommercialBuckets,
    getDropdownBucketOptionsForCharge,
    isCoreCommercialBucket,
} from "./spot-commercial-buckets.ts";

// ─── Helpers ────────────────────────────────────────────────────────────

function bucketIds(defs: Array<{ id: string }>): string[] {
    return defs.map(d => d.id);
}

let passed = 0;
let failed = 0;

function assert(condition: boolean, message: string): void {
    if (condition) {
        console.log(`✓ ${message}`);
        passed++;
    } else {
        console.error(`✗ FAIL: ${message}`);
        failed++;
    }
}

// ─── Test 1: Customs charge does not leak customs to other rows ──────

function testCustomsDoesNotLeakToOtherRows() {
    const customsCharge = {
        bucket: "origin_charges",
        description: "Customs clearance fee",
        code: "CUS001",
    };
    const freightCharge = {
        bucket: "airfreight",
        description: "Air freight rate",
        code: "AFR001",
    };
    const context = {
        missingComponents: [] as string[],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
    };

    // Customs charge should see customs in its own dropdown
    const customsOptions = getDropdownBucketOptionsForCharge(customsCharge, context);
    assert(
        bucketIds(customsOptions).includes("customs"),
        "Customs charge sees 'customs' in its own dropdown"
    );

    // Freight charge should NOT see customs in its dropdown
    const freightOptions = getDropdownBucketOptionsForCharge(freightCharge, context);
    assert(
        !bucketIds(freightOptions).includes("customs"),
        "Freight charge does NOT see 'customs' in its dropdown"
    );
}

// ─── Test 2: Pickup charge does not leak transport to other rows ─────

function testPickupDoesNotLeakTransportToOtherRows() {
    const pickupCharge = {
        bucket: "origin_charges",
        description: "Pickup cartage",
        code: "PKP001",
    };
    const handlingCharge = {
        bucket: "origin_charges",
        description: "Terminal handling",
        code: "THC001",
    };
    const context = {
        missingComponents: [] as string[],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
    };

    // Pickup charge should see transport in its own dropdown
    const pickupOptions = getDropdownBucketOptionsForCharge(pickupCharge, context);
    assert(
        bucketIds(pickupOptions).includes("transport"),
        "Pickup charge sees 'transport' in its own dropdown"
    );

    // Handling charge should NOT see transport
    const handlingOptions = getDropdownBucketOptionsForCharge(handlingCharge, context);
    assert(
        !bucketIds(handlingOptions).includes("transport"),
        "Handling charge does NOT see 'transport' in its dropdown"
    );
}

// ─── Test 3: Empty sub-buckets should not render as visible ──────────

function testEmptySubBucketsNotVisible() {
    // A form with only freight charges
    const charges = [
        { bucket: "airfreight", description: "Air freight rate" },
        { bucket: "airfreight", description: "Fuel surcharge" },
    ];

    const visible = getVisibleCommercialBuckets({
        missingComponents: [],
        serviceScope: "D2D",
        shipmentType: "EXPORT",
        charges,
    });

    const ids = bucketIds(visible);
    assert(!ids.includes("security"), "Empty security bucket is NOT visible");
    assert(!ids.includes("customs"), "Empty customs bucket is NOT visible");
    assert(!ids.includes("transport"), "Empty transport bucket is NOT visible");
    assert(!ids.includes("other"), "Empty other bucket is NOT visible");
}

// ─── Test 4: Empty Destination not visible unless required ───────────

function testEmptyDestinationNotVisibleUnlessRequired() {
    // A2A scope = only freight required, no destination
    const charges = [
        { bucket: "airfreight", description: "Air freight" },
    ];

    const visible = getVisibleCommercialBuckets({
        missingComponents: [],
        serviceScope: "A2A",
        shipmentType: "EXPORT",
        charges,
    });

    const ids = bucketIds(visible);
    assert(!ids.includes("destination"), "Empty destination NOT visible for A2A scope");
    assert(ids.includes("freight"), "Freight IS visible for A2A scope");

    // D2D scope = destination is required, so it appears even empty
    const visibleD2D = getVisibleCommercialBuckets({
        missingComponents: [],
        serviceScope: "D2D",
        shipmentType: "EXPORT",
        charges,
    });

    const idsD2D = bucketIds(visibleD2D);
    assert(idsD2D.includes("destination"), "Empty destination IS visible for D2D scope (required)");
}

// ─── Test 5: AWB/document charges infer to Origin Charges ────────────

function testAwbDocumentInferToOrigin() {
    const awbCharge = { bucket: "airfreight", description: "AWB fee" };
    assert(
        inferCommercialBucket(awbCharge) === "origin",
        "AWB fee infers to origin"
    );

    const docCharge = { bucket: "airfreight", description: "DOC handling" };
    assert(
        inferCommercialBucket(docCharge) === "origin",
        "DOC handling infers to origin"
    );

    const doxCharge = { bucket: "airfreight", description: "DOX shipment fee" };
    assert(
        inferCommercialBucket(doxCharge) === "origin",
        "DOX shipment fee infers to origin"
    );

    const originCharge = { bucket: "airfreight", description: "Origin handling" };
    assert(
        inferCommercialBucket(originCharge) === "origin",
        "Origin handling infers to origin"
    );

    const terminalCharge = { bucket: "airfreight", description: "Terminal charge" };
    assert(
        inferCommercialBucket(terminalCharge) === "origin",
        "Terminal charge infers to origin"
    );

    const agencyCharge = { bucket: "airfreight", description: "Agency fee" };
    assert(
        inferCommercialBucket(agencyCharge) === "origin",
        "Agency fee infers to origin"
    );
}

// ─── Test 6: isCoreCommercialBucket ──────────────────────────────────

function testIsCoreCommercialBucket() {
    assert(isCoreCommercialBucket("freight"), "freight is core");
    assert(isCoreCommercialBucket("origin"), "origin is core");
    assert(isCoreCommercialBucket("destination"), "destination is core");
    assert(!isCoreCommercialBucket("security"), "security is NOT core");
    assert(!isCoreCommercialBucket("customs"), "customs is NOT core");
    assert(!isCoreCommercialBucket("transport"), "transport is NOT core");
    assert(!isCoreCommercialBucket("other"), "other is NOT core");
}

// ─── Test 7: Per-charge dropdown always includes current bucket ──────

function testDropdownAlwaysIncludesCurrentBucket() {
    const securityCharge = {
        bucket: "airfreight",
        description: "X-ray screening",
    };
    const context = {
        missingComponents: [] as string[],
        serviceScope: "A2A",
        shipmentType: "EXPORT" as const,
    };

    // Even though A2A scope doesn't require local charges, x-ray charge
    // should still see "security" in its dropdown
    const options = getDropdownBucketOptionsForCharge(securityCharge, context);
    assert(
        bucketIds(options).includes("security"),
        "X-ray charge always sees 'security' in dropdown even for A2A scope"
    );
    // But should NOT see transport, customs, etc.
    assert(
        !bucketIds(options).includes("transport"),
        "X-ray charge does NOT see 'transport'"
    );
    assert(
        !bucketIds(options).includes("customs"),
        "X-ray charge does NOT see 'customs'"
    );
}

// ─── Test 8: Dropdown includes in-scope core buckets when active ──────

function testDropdownIncludesInScopeCoreBuckets() {
    const charge = {
        bucket: "airfreight",
        description: "Air freight",
    };
    const context = {
        missingComponents: ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
    };

    const options = getDropdownBucketOptionsForCharge(charge, context);
    const ids = bucketIds(options);
    assert(ids.includes("freight"), "D2D freight charge sees freight");
    assert(ids.includes("origin"), "D2D freight charge sees origin");
    assert(ids.includes("destination"), "D2D freight charge sees destination");
}

// ─── Test 9: Normal Air Freight SPOT review regression test ──────────

function testNormalAirFreightReview() {
    const charges = [
        { bucket: "airfreight", description: "Air freight rate", code: "AF" },
        { bucket: "origin_charges", description: "AWB Fee", code: "AWB" },
        { bucket: "origin_charges", description: "Documentation Fee", code: "DOC" },
        { bucket: "origin_charges", description: "Origin handling charge", code: "OHC" }
    ];
    const context = {
        missingComponents: ["ORIGIN_LOCAL", "FREIGHT"],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
        charges
    };

    const visible = getVisibleCommercialBuckets(context);
    const visibleIds = bucketIds(visible);

    assert(visibleIds.includes("freight"), "Freight card is visible");
    assert(visibleIds.includes("origin"), "Origin charges card is visible");
    assert(!visibleIds.includes("destination"), "Destination card is NOT visible");
    assert(!visibleIds.includes("security"), "Security card is NOT visible");
    assert(!visibleIds.includes("customs"), "Customs card is NOT visible");
    assert(!visibleIds.includes("transport"), "Transport card is NOT visible");
    assert(!visibleIds.includes("other"), "Other card is NOT visible");

    // Dropdown check for Freight row
    const freightOptions = getDropdownBucketOptionsForCharge(charges[0], context);
    const freightOptIds = bucketIds(freightOptions);
    assert(!freightOptIds.includes("customs"), "Freight row does not include Customs option");
    assert(!freightOptIds.includes("transport"), "Freight row does not include Transport option");
    assert(!freightOptIds.includes("security"), "Freight row does not include Security option");
    assert(!freightOptIds.includes("other"), "Freight row does not include Other option");

    // AWB/Doc rows infer Origin Charges
    assert(inferCommercialBucket(charges[1]) === "origin", "AWB fee row infers origin");
    assert(inferCommercialBucket(charges[2]) === "origin", "Doc fee row infers origin");
}

// ─── Test 10: Pickup Fee dropdown isolation regression test ──────────

function testPickupFeeDropdownIsolation() {
    const charges = [
        { bucket: "airfreight", description: "Air freight rate", code: "AF" },
        { bucket: "origin_charges", description: "Pickup Fee", code: "PKP" } // infers transport
    ];
    const context = {
        missingComponents: ["ORIGIN_LOCAL", "FREIGHT"],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
        charges
    };

    const visible = getVisibleCommercialBuckets(context);
    const visibleIds = bucketIds(visible);
    assert(visibleIds.includes("transport"), "Transport card IS visible due to Pickup Fee");

    const freightOptions = getDropdownBucketOptionsForCharge(charges[0], context);
    assert(!bucketIds(freightOptions).includes("transport"), "Freight row does NOT inherit transport option");

    const pickupOptions = getDropdownBucketOptionsForCharge(charges[1], context);
    assert(bucketIds(pickupOptions).includes("transport"), "Pickup row DOES get transport option");
}

// ─── Test 11: Customs Clearance dropdown isolation regression test ────

function testCustomsDropdownIsolation() {
    const charges = [
        { bucket: "airfreight", description: "Air freight rate", code: "AF" },
        { bucket: "origin_charges", description: "Customs Clearance", code: "CUS" } // infers customs
    ];
    const context = {
        missingComponents: ["ORIGIN_LOCAL", "FREIGHT"],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
        charges
    };

    const visible = getVisibleCommercialBuckets(context);
    const visibleIds = bucketIds(visible);
    assert(visibleIds.includes("customs"), "Customs card IS visible due to Customs Clearance");

    const freightOptions = getDropdownBucketOptionsForCharge(charges[0], context);
    assert(!bucketIds(freightOptions).includes("customs"), "Freight row does NOT inherit customs option");

    const customsOptions = getDropdownBucketOptionsForCharge(charges[1], context);
    assert(bucketIds(customsOptions).includes("customs"), "Customs row DOES get customs option");
}

// ─── Test 12: Empty Destination not visible unless required ───────────

function testEmptyDestinationNotVisibleWithoutInputRequirement() {
    const charges = [
        { bucket: "airfreight", description: "Air freight rate", code: "AF" }
    ];
    // Scope is D2D but missingComponents only has FREIGHT and ORIGIN_LOCAL (no destination required)
    const context = {
        missingComponents: ["FREIGHT", "ORIGIN_LOCAL"],
        serviceScope: "D2D",
        shipmentType: "EXPORT" as const,
        charges
    };

    const visible = getVisibleCommercialBuckets(context);
    assert(!bucketIds(visible).includes("destination"), "Empty destination NOT visible when destination input not required");
}

// ─── Run all tests ───────────────────────────────────────────────────

testCustomsDoesNotLeakToOtherRows();
testPickupDoesNotLeakTransportToOtherRows();
testEmptySubBucketsNotVisible();
testEmptyDestinationNotVisibleUnlessRequired();
testAwbDocumentInferToOrigin();
testIsCoreCommercialBucket();
testDropdownAlwaysIncludesCurrentBucket();
testDropdownIncludesInScopeCoreBuckets();
testNormalAirFreightReview();
testPickupFeeDropdownIsolation();
testCustomsDropdownIsolation();
testEmptyDestinationNotVisibleWithoutInputRequirement();

console.log("");
console.log("========================================================");
if (failed === 0) {
    console.log(`ALL ${passed} COMMERCIAL BUCKET TESTS PASSED SUCCESSFULLY!`);
} else {
    console.log(`FAILURES: ${failed} of ${passed + failed} tests failed.`);
    process.exit(1);
}
console.log("========================================================");
