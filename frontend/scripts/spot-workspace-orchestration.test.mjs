import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());
const workspacePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");
const hookPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "useSpotResolutionWorkflow.ts");
const apiPath = path.join(frontendRoot, "src", "lib", "api.ts");
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
const apiSrc = await readFile(apiPath, "utf8");
const panelSources = new Map(
    await Promise.all(
        panelNames.map(async panelName => [
            panelName,
            await readFile(path.join(frontendRoot, "src", "components", "spot", "workspace", `${panelName}.tsx`), "utf8")
        ])
    )
);
const mapExistingFormSrc = await readFile(path.join(frontendRoot, "src", "components", "spot", "workspace", "MapExistingForm.tsx"), "utf8");

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
assert.ok(hookSrc.includes('type: "resolve_source_finding"'), "Source findings must submit authoritative resolve decisions");
assert.ok(hookSrc.includes("Source finding resolution requires a non-empty review note"), "Source finding resolution must require a review note");
assert.ok(workspaceSrc.includes('currentIssue.type === "source_finding"'), "ExceptionWorkspace must render source finding blockers");
assert.ok(workspaceSrc.includes("Approve Source With Note"), "ExceptionWorkspace must expose source approval with note workflow");
assert.ok(hookSrc.includes("getDraftQuote"), "useSpotResolutionWorkflow must reload the Draft Quote after live unknown-item decisions");
assert.ok(hookSrc.includes("finalizeDraftQuoteReview"), "useSpotResolutionWorkflow must call finalizeDraftQuoteReview");
assert.ok(hookSrc.includes("reopenDraftQuoteReview"), "useSpotResolutionWorkflow must call reopenDraftQuoteReview for authorized live reopen");
assert.ok(apiSrc.includes("export async function reopenDraftQuoteReview"), "API client must expose reopenDraftQuoteReview");
assert.ok(apiSrc.includes("/draft-quote/reopen/"), "Reopen API client must target the existing reopen endpoint");
assert.ok(hookSrc.includes("useConfirmDialog"), "Reopen must require a confirmation dialog");
assert.ok(hookSrc.includes("REOPEN_ROLES") && hookSrc.includes("manager") && hookSrc.includes("admin"), "Reopen UI must be role-gated to manager/admin");
assert.ok(hookSrc.includes("state.reviewSession.status === \"finalized\""), "Reopen must only be available for finalized reviews");
assert.ok(hookSrc.includes("state.reviewSession.available_actions.includes(\"reopen\") || isReopenAuthorized"), "Reopen visibility must honor backend available_actions or authorized manager/admin role");
assert.ok(hookSrc.includes("Boolean(isLive && envelopeId)"), "Reopen must only be available in live workspaces");
assert.ok(hookSrc.includes("isReopeningReview || !canReopenReviewNow()"), "Duplicate reopen submissions must be blocked");
assert.ok(hookSrc.includes("await refreshLiveDraftQuote()"), "Successful reopen must reload the Draft Quote from the backend");
assert.ok(hookSrc.includes("API error reopening review"), "Failed reopen must display backend errors");
assert.ok(hookSrc.includes("setIsReopeningReview(true)") && hookSrc.includes("setIsReopeningReview(false)"), "Reopen must track in-flight submission state");
assert.ok(hookSrc.includes('dispatch({ type: "SET_ACTION_MESSAGE", payload: "Draft Quote review reopened. Workspace is editable again." })'), "Successful reopen must show a clear success message");
assert.ok(hookSrc.indexOf("const { reopenDraftQuoteReview }") > hookSrc.indexOf("if (isReopeningReview || !canReopenReviewNow())"), "Demo/unauthorized reopen must return before importing the live API client");
assert.ok(hookSrc.includes('type: "classify_unclassified"'), "Unknown-item live actions must submit classify_unclassified decisions");
assert.ok(!hookSrc.includes('type: "map_to_product_code",\n            target_id: itemId'), "Unknown-item mapping must not submit map_to_product_code with an unclassified item ID");
assert.ok(!hookSrc.includes('newChargeId = `chg-new-${Date.now()}`;\n            try'), "Live unknown charge creation must not create synthetic IDs");
assert.ok(!hookSrc.includes('domain: "IMPORT"'), "ProductCode requests must not hardcode IMPORT domain");
assert.ok(hookSrc.includes("resolveProductCodeDomainFromDraftQuote(initialData.shipment_context)"), "ProductCode request domain must come from Draft Quote route evidence");
assert.ok(hookSrc.includes("domain: productCodeDomain"), "ProductCode requests must include derived domain in details");
assert.ok(hookSrc.includes("productCodeDomainResolution.issueMessage"), "ProductCode requests must fail visibly with specific route evidence diagnostics");
assert.ok(hookSrc.includes("Backend rejected ProductCode request"), "Backend ProductCode request rejection must remain visible after submission");
assert.ok(!hookSrc.includes('currency: "SGD"'), "Unknown ProductCode requests must not hardcode SGD currency");
assert.ok(workspaceSrc.includes("actions.openUnknownMapExisting"), "Unknown Map Existing must open a detail-collection workflow instead of submitting from ProductCode-only selection");
assert.ok(workspaceSrc.includes('collectChargeDetails={currentIssue.type === "unknown_charge"}'), "Unknown Map Existing must collect full charge details");
assert.ok(mapExistingFormSrc.includes("Confirm Mapping"), "MapExistingForm must require confirmation when collecting unknown charge details");
assert.ok(mapExistingFormSrc.includes("collectChargeDetails"), "MapExistingForm must support the unknown charge detail collection mode");
assert.ok(hookSrc.includes("return response;"), "submitLiveDecision must return the resolve response");
assert.ok(hookSrc.includes("rejected_decisions.find"), "submitLiveDecision must inspect rejected_decisions for the submitted decision");
assert.ok(hookSrc.includes("throw new Error(rejectedMessage)"), "submitLiveDecision must throw rejected decision messages without refreshing state");
assert.ok(hookSrc.includes("chargeLabel === GENERIC_UNKNOWN_LABEL"), "Unknown Map Existing must never submit the generic Unknown Charge Block label");
assert.ok(hookSrc.includes("Complete charge label, bucket, currency, amount, unit and ProductCode"), "Unknown Map Existing must require a complete charge payload");
assert.ok(hookSrc.includes("category: state.requestForm.bucket"), "ProductCode requests must carry bucket metadata for compatibility");

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
    "onFinalizeReview={actions.finalizeReview}",
    "onReopenReview={actions.reopenReview}"
];
for (const callbackBinding of parentBoundCallbacks) {
    assert.ok(workspaceSrc.includes(callbackBinding), `ExceptionWorkspace must keep callback binding ${callbackBinding}`);
}

console.log("✓ Verified extracted panels receive parent-bound callbacks.");

console.log("All Spot Workspace Orchestration contract assertions passed successfully!");
