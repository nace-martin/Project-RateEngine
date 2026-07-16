import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());
const workspacePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");
const hookPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "useSpotResolutionWorkflow.ts");

console.log("Starting Spot Workspace Orchestration Contract Assertions...");

const workspaceSrc = await readFile(workspacePath, "utf8");
const hookSrc = await readFile(hookPath, "utf8");

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
assert.ok(hookSrc.includes("finalizeDraftQuoteReview"), "useSpotResolutionWorkflow must call finalizeDraftQuoteReview");

console.log("✓ Verified useSpotResolutionWorkflow owns resolve and finalization API calls.");

console.log("All Spot Workspace Orchestration contract assertions passed successfully!");
