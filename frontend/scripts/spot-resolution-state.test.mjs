import assert from "node:assert/strict";
import path from "node:path";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const statePath = path.join(frontendRoot, "src", "components", "spot", "workspace", "spotResolutionState.ts");

console.log("Transpiling spotResolutionState.ts...");

function transpile(source, fileName) {
    return ts.transpileModule(source, {
        compilerOptions: {
            module: ts.ModuleKind.ESNext,
            target: ts.ScriptTarget.ES2022,
        },
        fileName,
    }).outputText;
}

const stateSrc = await readFile(statePath, "utf8");
// Remove the type-only imports so ES module execution does not try to load draft-quote-types
const cleanedSource = stateSrc.replace(/import\s+[\s\S]*?\s+from\s+['"].*?draft-quote-types['"];?/g, "");
const transpiledJs = transpile(cleanedSource, statePath);

const base64Data = Buffer.from(transpiledJs).toString("base64");
const moduleUrl = `data:text/javascript;base64,${base64Data}`;
const {
    createSpotResolutionState,
    spotResolutionReducer,
    selectCombinedUnresolved,
    selectCurrentIssue,
    selectActiveCharges,
    selectUniqueCurrencies,
    selectSubtotals,
    selectChecklistIssuesResolved,
    selectChecklistNoUnknown,
    selectChecklistProductCodesVerified,
    selectCanFinishReview,
    selectIsReviewLocked,
    selectCanUsePrototypeOverride,
    selectNextStepGuidance
} = await import(moduleUrl);

console.log("Starting Spot Resolution State Reducer & Selector Unit Tests...");

// 1. Setup Mock DraftQuote data
const mockInitialQuote = {
    quote_summary: "Test Summary",
    suggested_charges: [
        {
            id: "c1",
            status: "suggested",
            display_label: "Air Cargo Handling",
            raw_label: "Air Cargo Handling",
            suggested_product_code: null,
            product_code_conflict: true,
            bucket: "origin_charges",
            currency: "USD",
            amount: 100,
            unit: "kg",
            include_in_totals: true,
            conditions: [],
            warnings: []
        },
        {
            id: "c2",
            status: "suggested",
            display_label: "Fuel Surcharge",
            raw_label: "Fuel Surcharge",
            suggested_product_code: "AF-FUEL",
            product_code_conflict: false,
            bucket: "origin_charges",
            currency: "USD",
            amount: 50,
            unit: "flat",
            include_in_totals: true,
            conditions: [],
            warnings: []
        }
    ],
    review_queue: [
        { id: "c1", type: "charge_needs_review", message: "Mapping missing" }
    ],
    unclassified_items: [
        { id: "u1", raw_text: "SGD 25 docs fee", evidence: null, review_reason: "unmatched_text" }
    ],
    ignored_items: [],
    totals_validation: {
        difference: 0,
        calculated_total: 150,
        extracted_total: 150
    },
    commercial_terms: []
};

// 2. Test Initial State Creation
const initialState = createSpotResolutionState(mockInitialQuote);
assert.equal(initialState.suggestedCharges.length, 2);
assert.equal(initialState.reviewQueue.length, 1);
assert.equal(initialState.unclassifiedItems.length, 1);
assert.equal(initialState.decisions.length, 0);
assert.equal(initialState.activeIssueId, "c1"); // Fallback to first review queue blocker
assert.equal(initialState.reviewSession.status, "draft");
console.log("✓ Initial state created successfully.");

// 3. Test SELECT_ISSUE action
{
    const state = spotResolutionReducer(initialState, { type: "SELECT_ISSUE", payload: { issueId: "u1" } });
    assert.equal(state.activeIssueId, "u1");
    assert.equal(state.unknownWizard.step, 1);
    console.log("✓ SELECT_ISSUE action transitions correctly.");
}

// 4. Test MAP_PRODUCT_CODE action
{
    const state = spotResolutionReducer(initialState, {
        type: "MAP_PRODUCT_CODE",
        payload: { chargeId: "c1", productCode: "AF-FREIGHT", displayLabel: "Air Cargo Handling" }
    });
    const charge = state.suggestedCharges.find(c => c.id === "c1");
    assert.equal(charge.suggested_product_code, "AF-FREIGHT");
    assert.equal(charge.status, "accepted_by_user");
    assert.equal(state.reviewQueue.length, 0);
    assert.equal(state.decisions.length, 1);
    assert.equal(state.decisions[0].type, "map");
    assert.equal(state.selectedActionType, null);
    console.log("✓ MAP_PRODUCT_CODE resolves charge blocker and logs decision.");
}

// 5. Test USE_APPROVED_PRODUCT_CODE action
{
    const initialWithApproved = {
        ...initialState,
        suggestedCharges: initialState.suggestedCharges.map(c =>
            c.id === "c1" ? { ...c, product_code_request_id: 10, approved_product_code_id: 20, approved_product_code: "AF-HC" } : c
        )
    };
    const state = spotResolutionReducer(initialWithApproved, {
        type: "USE_APPROVED_PRODUCT_CODE",
        payload: { chargeId: "c1", code: "AF-HC", displayLabel: "Air Cargo Handling" }
    });
    const charge = state.suggestedCharges.find(c => c.id === "c1");
    assert.equal(charge.suggested_product_code, "AF-HC");
    assert.equal(charge.status, "accepted_by_user");
    console.log("✓ USE_APPROVED_PRODUCT_CODE applies approved mappings.");
}

// 6. Test ACCEPT_SUGGESTED_MAPPING action
{
    const state = spotResolutionReducer(initialState, {
        type: "ACCEPT_SUGGESTED_MAPPING",
        payload: { chargeId: "c2", displayLabel: "Fuel Surcharge", suggestedCode: "AF-FUEL" }
    });
    const charge = state.suggestedCharges.find(c => c.id === "c2");
    assert.equal(charge.status, "accepted_by_user");
    console.log("✓ ACCEPT_SUGGESTED_MAPPING updates suggestion status.");
}

// 7. Test SUBMIT_PRODUCT_CODE_REQUEST action
{
    const state = spotResolutionReducer(initialState, {
        type: "SUBMIT_PRODUCT_CODE_REQUEST",
        payload: { chargeId: "c1", proposedCode: "AF-SPECIAL", sourceText: "Special handler text" }
    });
    const charge = state.suggestedCharges.find(c => c.id === "c1");
    assert.equal(charge.status, "pending_product_code");
    assert.equal(state.reviewQueue.length, 0);
    console.log("✓ SUBMIT_PRODUCT_CODE_REQUEST sets status to pending.");
}

// 8. Test IGNORE_CHARGE action
{
    const state = spotResolutionReducer(initialState, {
        type: "IGNORE_CHARGE",
        payload: { chargeId: "c1", displayLabel: "Air Cargo Handling", rawLabel: "Air Cargo Handling", evidence: null }
    });
    const charge = state.suggestedCharges.find(c => c.id === "c1");
    assert.equal(charge.status, "ignored");
    assert.equal(charge.include_in_totals, false);
    assert.equal(state.ignoredItems.length, 1);
    assert.equal(state.reviewQueue.length, 0);
    console.log("✓ IGNORE_CHARGE excludes charge and archives it.");
}

// 9. Test IGNORE_UNKNOWN_CHARGE action
{
    const state = spotResolutionReducer(initialState, {
        type: "IGNORE_UNKNOWN_CHARGE",
        payload: { itemId: "u1", rawText: "SGD 25 docs fee", evidence: null }
    });
    assert.equal(state.unclassifiedItems.length, 0);
    assert.equal(state.ignoredItems.length, 1);
    console.log("✓ IGNORE_UNKNOWN_CHARGE excludes unknown blocks.");
}

// 10. Test APPROVE_UNKNOWN_NOTE action
{
    const state = spotResolutionReducer(initialState, {
        type: "APPROVE_UNKNOWN_NOTE",
        payload: { itemId: "u1", rawText: "SGD 25 docs fee" }
    });
    assert.equal(state.unclassifiedItems.length, 0);
    assert.equal(state.ignoredItems.length, 0);
    console.log("✓ APPROVE_UNKNOWN_NOTE handles condition note files.");
}

// 11. Test ADD_UNKNOWN_AS_CHARGE actions (with & without mapping code)
{
    // Case A: With ProductCode mapping -> should NOT add blocker in review queue
    const stateWithPC = spotResolutionReducer(initialState, {
        type: "ADD_UNKNOWN_AS_CHARGE",
        payload: {
            itemId: "u1",
            newChargeId: "chg-added-1",
            chargeName: "Docs Fee",
            chargeBucket: "destination_charges",
            chargeCurrency: "SGD",
            chargeAmount: 25,
            chargeUnit: "flat",
            chargeProductCode: "AF-HC",
            evidence: null
        }
    });
    assert.equal(stateWithPC.suggestedCharges.length, 3);
    assert.equal(stateWithPC.unclassifiedItems.length, 0);
    assert.equal(stateWithPC.reviewQueue.length, 1); // Remains 1 (original blocker only)
    const addedWithPC = stateWithPC.suggestedCharges.find(c => c.id === "chg-added-1");
    assert.equal(addedWithPC.suggested_product_code, "AF-HC");
    assert.equal(addedWithPC.status, "accepted_by_user");

    // Case B: Without ProductCode mapping -> should add a new blocker in review queue
    const stateNoPC = spotResolutionReducer(initialState, {
        type: "ADD_UNKNOWN_AS_CHARGE",
        payload: {
            itemId: "u1",
            newChargeId: "chg-added-2",
            chargeName: "Docs Fee No PC",
            chargeBucket: "destination_charges",
            chargeCurrency: "SGD",
            chargeAmount: 25,
            chargeUnit: "flat",
            chargeProductCode: "",
            evidence: null
        }
    });
    assert.equal(stateNoPC.suggestedCharges.length, 3);
    assert.equal(stateNoPC.unclassifiedItems.length, 0);
    assert.equal(stateNoPC.reviewQueue.length, 2); // Blockers increased!
    const addedNoPC = stateNoPC.suggestedCharges.find(c => c.id === "chg-added-2");
    assert.equal(addedNoPC.suggested_product_code, null);
    assert.equal(addedNoPC.status, "suggested");
    console.log("✓ ADD_UNKNOWN_AS_CHARGE correctly maps blockers.");
}

// 12. Test TOGGLE_INCLUDE_IN_TOTALS action
{
    const state = spotResolutionReducer(initialState, { type: "TOGGLE_INCLUDE_IN_TOTALS", payload: { chargeId: "c2" } });
    const charge = state.suggestedCharges.find(c => c.id === "c2");
    assert.equal(charge.include_in_totals, false);
    console.log("✓ TOGGLE_INCLUDE_IN_TOTALS action works.");
}

// 13. Test UNDO_DECISION action
{
    // Apply MAP_PRODUCT_CODE first
    const resolvedState = spotResolutionReducer(initialState, {
        type: "MAP_PRODUCT_CODE",
        payload: { chargeId: "c1", productCode: "AF-FREIGHT", displayLabel: "Air Cargo Handling" }
    });
    assert.equal(resolvedState.decisions.length, 1);
    
    // Undo
    const undoneState = spotResolutionReducer(resolvedState, {
        type: "UNDO_DECISION",
        payload: { decisionId: "c1" }
    });
    assert.equal(undoneState.decisions.length, 0);
    assert.equal(undoneState.reviewQueue.length, 1);
    assert.equal(undoneState.suggestedCharges.find(c => c.id === "c1").suggested_product_code, null);
    console.log("✓ UNDO_DECISION restores original lists from decision snapshot.");
}

// 14. Test selectors calculations: checklist completion and subtotals splitting
{
    // Before resolutions:
    assert.equal(selectChecklistIssuesResolved(initialState), false);
    assert.equal(selectChecklistNoUnknown(initialState), false);
    assert.equal(selectCanFinishReview(initialState), false);
    assert.deepEqual(selectUniqueCurrencies(initialState), ["USD"]);
    assert.deepEqual(selectSubtotals(initialState), { USD: 150 });
    assert.equal(selectNextStepGuidance(initialState), "Next step: Choose a ProductCode for Air Cargo Handling.");

    // Complete resolutions
    let resolvedState = spotResolutionReducer(initialState, {
        type: "MAP_PRODUCT_CODE",
        payload: { chargeId: "c1", productCode: "AF-FREIGHT", displayLabel: "Air Cargo Handling" }
    });
    resolvedState = spotResolutionReducer(resolvedState, {
        type: "APPROVE_UNKNOWN_NOTE",
        payload: { itemId: "u1", rawText: "note text" }
    });

    assert.equal(selectChecklistIssuesResolved(resolvedState), true);
    assert.equal(selectChecklistNoUnknown(resolvedState), true);
    assert.equal(selectChecklistProductCodesVerified(resolvedState), true);
    assert.equal(selectCanFinishReview(resolvedState), true);
    assert.equal(selectNextStepGuidance(resolvedState), "Review the remaining commercial term before finishing.");

    // Test multiple currencies totals splitting
    const multiCurrencyState = {
        ...resolvedState,
        suggestedCharges: [
            ...resolvedState.suggestedCharges,
            {
                id: "c3",
                status: "accepted_by_user",
                display_label: "Handling",
                currency: "SGD",
                amount: 30,
                include_in_totals: true
            }
        ]
    };
    assert.deepEqual(selectUniqueCurrencies(multiCurrencyState), ["USD", "SGD"]);
    assert.deepEqual(selectSubtotals(multiCurrencyState), { USD: 150, SGD: 30 });
    console.log("✓ Selector subtotal groupings and checklist eligibility validated.");
}

// 15. Test FINALIZE_REVIEW locking
{
    const state = spotResolutionReducer(initialState, {
        type: "FINALIZE_REVIEW",
        payload: {
            status: "finalized",
            finalized_by: 1,
            finalized_at: "2026-07-16T12:00:00Z",
            remaining_blockers: 0,
            available_actions: ["reopen"]
        }
    });
    assert.equal(selectIsReviewLocked(state), true);
    console.log("✓ FINALIZE_REVIEW transitions and lock checks complete.");
}

// 16. Regression: review-item actions must NOT reset unknownWizard state
// Phase 14C had independent state for unknownStep/unknownClassification.
// These actions operate on DraftCharge review items, not on unknownWizard items.
// A mixed queue (review items + unknown items) means the wizard must retain its
// classification and step while the operator resolves review-item blockers.
{
    const wizardInProgress = {
        ...initialState,
        unknownWizard: { step: 2, classification: "charge" }
    };

    // MAP_PRODUCT_CODE must not touch unknownWizard
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "MAP_PRODUCT_CODE",
            payload: { chargeId: "c1", productCode: "AF-FREIGHT", displayLabel: "Air Cargo Handling" }
        });
        assert.equal(state.unknownWizard.step, 2, "MAP_PRODUCT_CODE must preserve unknownWizard.step");
        assert.equal(state.unknownWizard.classification, "charge", "MAP_PRODUCT_CODE must preserve unknownWizard.classification");
        console.log("✓ MAP_PRODUCT_CODE preserves unknownWizard state (parity regression).");
    }

    // SUBMIT_PRODUCT_CODE_REQUEST must not touch unknownWizard
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "SUBMIT_PRODUCT_CODE_REQUEST",
            payload: { chargeId: "c1", proposedCode: "AF-SPECIAL", sourceText: "Special handler text" }
        });
        assert.equal(state.unknownWizard.step, 2, "SUBMIT_PRODUCT_CODE_REQUEST must preserve unknownWizard.step");
        assert.equal(state.unknownWizard.classification, "charge", "SUBMIT_PRODUCT_CODE_REQUEST must preserve unknownWizard.classification");
        console.log("✓ SUBMIT_PRODUCT_CODE_REQUEST preserves unknownWizard state (parity regression).");
    }

    // USE_APPROVED_PRODUCT_CODE must not touch unknownWizard
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "USE_APPROVED_PRODUCT_CODE",
            payload: { chargeId: "c1", code: "AF-HC", displayLabel: "Air Cargo Handling" }
        });
        assert.equal(state.unknownWizard.step, 2, "USE_APPROVED_PRODUCT_CODE must preserve unknownWizard.step");
        assert.equal(state.unknownWizard.classification, "charge", "USE_APPROVED_PRODUCT_CODE must preserve unknownWizard.classification");
        console.log("✓ USE_APPROVED_PRODUCT_CODE preserves unknownWizard state (parity regression).");
    }

    // ACCEPT_SUGGESTED_MAPPING must not touch unknownWizard
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "ACCEPT_SUGGESTED_MAPPING",
            payload: { chargeId: "c2", displayLabel: "Fuel Surcharge", suggestedCode: "AF-FUEL" }
        });
        assert.equal(state.unknownWizard.step, 2, "ACCEPT_SUGGESTED_MAPPING must preserve unknownWizard.step");
        assert.equal(state.unknownWizard.classification, "charge", "ACCEPT_SUGGESTED_MAPPING must preserve unknownWizard.classification");
        console.log("✓ ACCEPT_SUGGESTED_MAPPING preserves unknownWizard state (parity regression).");
    }

    // IGNORE_CHARGE must not touch unknownWizard
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "IGNORE_CHARGE",
            payload: { chargeId: "c1", displayLabel: "Air Cargo Handling", rawLabel: "Air Cargo Handling", evidence: null }
        });
        assert.equal(state.unknownWizard.step, 2, "IGNORE_CHARGE must preserve unknownWizard.step");
        assert.equal(state.unknownWizard.classification, "charge", "IGNORE_CHARGE must preserve unknownWizard.classification");
        console.log("✓ IGNORE_CHARGE preserves unknownWizard state (parity regression).");
    }
}

// 17. Regression: unknown-item completion actions and UNDO must reset unknownWizard
// This verifies that the wizard IS reset by the actions that actually complete an
// unknown-item resolution workflow.
{
    const wizardInProgress = {
        ...initialState,
        unknownWizard: { step: 2, classification: "note" }
    };

    // IGNORE_UNKNOWN_CHARGE completes the unknown item flow — wizard should reset
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "IGNORE_UNKNOWN_CHARGE",
            payload: { itemId: "u1", rawText: "SGD 25 docs fee", evidence: null }
        });
        assert.equal(state.unknownWizard.step, 1, "IGNORE_UNKNOWN_CHARGE must reset unknownWizard.step to 1");
        assert.equal(state.unknownWizard.classification, null, "IGNORE_UNKNOWN_CHARGE must reset unknownWizard.classification to null");
        console.log("✓ IGNORE_UNKNOWN_CHARGE resets unknownWizard on completion.");
    }

    // APPROVE_UNKNOWN_NOTE completes the note flow — wizard should reset
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "APPROVE_UNKNOWN_NOTE",
            payload: { itemId: "u1", rawText: "SGD 25 docs fee" }
        });
        assert.equal(state.unknownWizard.step, 1, "APPROVE_UNKNOWN_NOTE must reset unknownWizard.step to 1");
        assert.equal(state.unknownWizard.classification, null, "APPROVE_UNKNOWN_NOTE must reset unknownWizard.classification to null");
        console.log("✓ APPROVE_UNKNOWN_NOTE resets unknownWizard on completion.");
    }

    // ADD_UNKNOWN_AS_CHARGE completes the add-charge flow — wizard should reset
    {
        const state = spotResolutionReducer(wizardInProgress, {
            type: "ADD_UNKNOWN_AS_CHARGE",
            payload: {
                itemId: "u1",
                newChargeId: "chg-wizard-test",
                chargeName: "Docs Fee",
                chargeBucket: "destination_charges",
                chargeCurrency: "SGD",
                chargeAmount: 25,
                chargeUnit: "flat",
                chargeProductCode: "AF-HC",
                evidence: null
            }
        });
        assert.equal(state.unknownWizard.step, 1, "ADD_UNKNOWN_AS_CHARGE must reset unknownWizard.step to 1");
        assert.equal(state.unknownWizard.classification, null, "ADD_UNKNOWN_AS_CHARGE must reset unknownWizard.classification to null");
        console.log("✓ ADD_UNKNOWN_AS_CHARGE resets unknownWizard on completion.");
    }

    // UNDO_DECISION on an unknown-item resolution — wizard should reset
    {
        // First resolve the unknown item
        const resolvedState = spotResolutionReducer(initialState, {
            type: "IGNORE_UNKNOWN_CHARGE",
            payload: { itemId: "u1", rawText: "SGD 25 docs fee", evidence: null }
        });
        // Set wizard mid-step on a subsequent issue
        const wizardMidStep = { ...resolvedState, unknownWizard: { step: 2, classification: "charge" } };
        const undoneState = spotResolutionReducer(wizardMidStep, {
            type: "UNDO_DECISION",
            payload: { decisionId: "u1" }
        });
        assert.equal(undoneState.unknownWizard.step, 1, "UNDO_DECISION must reset unknownWizard.step to 1");
        assert.equal(undoneState.unknownWizard.classification, null, "UNDO_DECISION must reset unknownWizard.classification to null");
        console.log("✓ UNDO_DECISION resets unknownWizard correctly.");
    }
}

console.log("All Spot Resolution State unit tests passed successfully!");

