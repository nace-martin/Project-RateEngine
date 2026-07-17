import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());
const workspacePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");
const hookPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "useSpotResolutionWorkflow.ts");
const panelNames = [
    "NeedsAttentionPanel",
    "ReviewDecisionsPanel",
    "VerificationWarningsPanel",
    "IgnoredItemsPanel",
    "FinalReviewPanel"
];

console.log("Starting Spot Workspace Orchestration Contract Assertions...");

const workspaceSrc = await readFile(workspacePath, "utf8");
const hookSrc = await readFile(hookPath, "utf8");
const panelSources = new Map(
    await Promise.all(
        panelNames.map(async panelName => [
            panelName,
            await readFile(path.join(frontendRoot, "src", "components", "spot", "workspace", `${panelName}.tsx`), "utf8")
        ])
    )
);

// 1. Verify ExceptionWorkspace imports and consumes the hook
assert.ok(
  workspaceSrc.includes('import { useSpotResolutionWorkflow } from "./workspace/useSpotResolutionWorkflow";'),
  "ExceptionWorkspace must import useSpotResolutionWorkflow"
);
assert.ok(
  workspaceSrc.includes("useSpotResolutionWorkflow({ initialData, isLive, envelopeId })") ||
  workspaceSrc.includes("useSpotResolutionWorkflow({\n        initialData,\n        isLive,\n        envelopeId\n    })"),
  "ExceptionWorkspace must invoke useSpotResolutionWorkflow with parameters"
);

console.log("✓ Verified useSpotResolutionWorkflow is imported and consumed by ExceptionWorkspace.");

// 1b. Verify presentation panels are imported and rendered by ExceptionWorkspace
for (const panelName of panelNames) {
    assert.ok(
        workspaceSrc.includes(`import { ${panelName} } from "./workspace/${panelName}";`),
        `ExceptionWorkspace must import ${panelName}`
    );
    assert.ok(
        workspaceSrc.includes(`<${panelName}`),
        `ExceptionWorkspace must render ${panelName}`
    );
}

console.log("✓ Verified extracted presentation panels are imported and rendered by ExceptionWorkspace.");

// 2. Verify state and handler functions are NOT declared inside ExceptionWorkspace anymore
const forbiddenStates = [
    "setSuggestedCharges",
    "setReviewQueue",
    "setUnclassifiedItems",
    "setIgnoredItems",
    "setDecisions",
    "setReviewSession",
    "setActiveIssueId",
    "setSelectedActionType",
    "setReqLabel",
    "setReqSource",
    "setReqCurrency",
    "setReqAmount",
    "setUnknownStep",
    "setUnknownClassification",
    "setAddName",
    "setAddBucket",
    "setAddCurrency",
    "setAddAmount",
    "setAddUnit",
    "setAddProductCode",
    "setActionMessage",
    "setPrototypeOverride"
];

for (const stateName of forbiddenStates) {
    // Assert they are not defined via useState inside the ExceptionWorkspace component
    const useStatePattern = new RegExp(`const\\s*\\[\\s*\\w+\\s*,\\s*${stateName}\\s*\\]\\s*=\\s*useState`);
    assert.ok(!useStatePattern.test(workspaceSrc), `ExceptionWorkspace must not locally declare state setter ${stateName}`);
}

console.log("✓ Verified ExceptionWorkspace does not locally declare resolution state variables.");

// 3. Verify handlers are not locally declared inside ExceptionWorkspace
const forbiddenHandlers = [
    "const handleMapProductCode =",
    "const handleSubmitProductCodeRequest =",
    "const handleAddUnknownAsCharge =",
    "const handleUseApprovedProductCode =",
    "const handleAcceptSuggestedMapping =",
    "const handleIgnoreCharge =",
    "const handleIgnoreUnknownCharge =",
    "const handleFinalizeReview =",
    "const handleUndoDecision =",
    "const captureSnapshot =",
    "const submitLiveDecision ="
];

for (const handlerName of forbiddenHandlers) {
    assert.ok(!workspaceSrc.includes(handlerName), `ExceptionWorkspace must not locally declare handler: ${handlerName}`);
}

console.log("✓ Verified ExceptionWorkspace does not locally declare resolution handler functions.");

// 4. Verify hook owns the API calls
assert.ok(hookSrc.includes('import("../../../lib/api")'), "useSpotResolutionWorkflow hook must import API functions");
assert.ok(hookSrc.includes("resolveDraftQuoteDecisions"), "useSpotResolutionWorkflow must call resolveDraftQuoteDecisions");
assert.ok(hookSrc.includes("getDraftQuote"), "useSpotResolutionWorkflow must reload the Draft Quote after live unknown-item decisions");
assert.ok(hookSrc.includes("finalizeDraftQuoteReview"), "useSpotResolutionWorkflow must call finalizeDraftQuoteReview");
assert.ok(hookSrc.includes('type: "classify_unclassified"'), "Unknown-item live actions must submit classify_unclassified decisions");
assert.ok(!hookSrc.includes('type: "map_to_product_code",\n            target_id: itemId'), "Unknown-item mapping must not submit map_to_product_code with an unclassified item ID");
assert.ok(!hookSrc.includes('newChargeId = `chg-new-${Date.now()}`;\n            try'), "Live unknown charge creation must not create synthetic IDs");
assert.ok(!hookSrc.includes('domain: "IMPORT"'), "ProductCode requests must not hardcode IMPORT domain");
assert.ok(!hookSrc.includes('currency: "SGD"'), "Unknown ProductCode requests must not hardcode SGD currency");

console.log("✓ Verified useSpotResolutionWorkflow owns resolve and finalization API calls.");

// 5. Verify extracted presentation panels are stateless and do not own workflow/API behavior
for (const [panelName, panelSrc] of panelSources) {
    assert.ok(!panelSrc.includes("useSpotResolutionWorkflow"), `${panelName} must not import or call workflow hook`);
    assert.ok(!panelSrc.includes("useState("), `${panelName} must not own local React state`);
    assert.ok(!/import.*from.*(api|lib\/api)/i.test(panelSrc), `${panelName} must not import API clients`);
    assert.ok(!panelSrc.includes("fetch("), `${panelName} must not perform fetch operations`);
    assert.ok(!panelSrc.includes("resolveDraftQuoteDecisions"), `${panelName} must not call resolve API`);
    assert.ok(!panelSrc.includes("finalizeDraftQuoteReview"), `${panelName} must not call finalize API`);
}

console.log("✓ Verified extracted presentation panels are stateless and API-free.");

// 6. Verify resolution callbacks remain parent-bound through the actions object
const parentBoundCallbacks = [
    "onSelectIssue={actions.selectIssue}",
    "onUndoDecision={actions.undoDecision}",
    "onTogglePrototypeOverride={actions.togglePrototypeOverride}",
    "onFinalizeReview={actions.finalizeReview}"
];
for (const callbackBinding of parentBoundCallbacks) {
    assert.ok(workspaceSrc.includes(callbackBinding), `ExceptionWorkspace must keep callback binding ${callbackBinding}`);
}

console.log("✓ Verified extracted panels receive parent-bound callbacks.");

console.log("All Spot Workspace Orchestration contract assertions passed successfully!");
