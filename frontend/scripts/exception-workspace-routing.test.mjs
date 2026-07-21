import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());
const spotPagePath = path.join(frontendRoot, "src", "app", "quotes", "spot", "[speId]", "page.tsx");
const livePagePath = path.join(frontendRoot, "src", "app", "quotes", "spot", "[speId]", "exception-workspace", "page.tsx");
const demoPagePath = path.join(frontendRoot, "src", "app", "quotes", "spot", "exception-workspace-demo", "page.tsx");
const workspacePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");
const finalReviewPanelPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "FinalReviewPanel.tsx");

const hookPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "useSpotResolutionWorkflow.ts");
const statePath = path.join(frontendRoot, "src", "components", "spot", "workspace", "spotResolutionState.ts");

const [spotPage, livePage, demoPage, workspace, finalReviewPanel, hook, stateFile] = await Promise.all([
  readFile(spotPagePath, "utf8"),
  readFile(livePagePath, "utf8"),
  readFile(demoPagePath, "utf8"),
  readFile(workspacePath, "utf8"),
  readFile(finalReviewPanelPath, "utf8"),
  readFile(hookPath, "utf8"),
  readFile(statePath, "utf8"),
]);

assert.ok(
  !spotPage.includes("Review in Exception Workspace"),
  "normal SPOT flow must not expose a manual Exception Workspace choice",
);

assert.match(
  spotPage,
  /router\.replace\(`\/quotes\/spot\/\$\{speId\}\/exception-workspace`\)/,
  "successful analysis and review-ready envelopes must replace into the live workspace route",
);

assert.match(
  spotPage,
  /shouldRedirectToExceptionWorkspace[\s\S]*state\.spe\.charges\.length > 0/,
  "base SPOT route must redirect existing imported-charge envelopes to the Exception Workspace",
);

assert.match(
  spotPage,
  /setCurrentStep\("intake"\)/,
  "new or explicitly edited SPEs must remain on intake",
);

assert.match(
  livePage,
  /const speId = params\?\.speId as string;/,
  "live workspace route must require the dynamic envelope ID",
);

assert.match(
  livePage,
  /getDraftQuote\(speId\)/,
  "live workspace route must load the backend Draft Quote payload for the envelope",
);

assert.match(
  livePage,
  /getSpotEnvelope\(speId\)/,
  "live workspace route must load the SPE context needed for safe quote creation",
);

assert.match(
  livePage,
  /<ExceptionWorkspace initialData=\{data\} isLive=\{true\} envelopeId=\{speId\} envelope=\{envelope\} \/>/,
  "live workspace must pass real payload, envelope ID, and SPE context into the workspace component",
);

assert.match(
  demoPage,
  /import\s+\{\s*hardCaseAirImportData\s*\}\s+from\s+["'].*hardCaseAirImport["']/,
  "demo route must import hardCaseAirImportData"
);

assert.match(
  demoPage,
  /initialData=\{hardCaseAirImportData\}/,
  "demo route must pass initialData={hardCaseAirImportData} explicitly"
);

assert.ok(
  !demoPage.includes("isLive={true}"),
  "demo route must not pass isLive={true}"
);

assert.match(
  hook,
  /type: "accept_suggestion"/,
  "live accept-suggestion actions must persist through the Draft Quote resolve API",
);

assert.match(
  stateFile,
  /!isLive\s*&&\s*state\.prototypeOverride/,
  "prototype finalization override must be disabled in live workspace mode",
);

assert.match(
  workspace,
  /<FinalReviewPanel[\s\S]*isLive=\{isLive\}/,
  "ExceptionWorkspace must pass isLive into the final review panel"
);

assert.match(
  workspace,
  /Back to Intake to edit source input/,
  "live workspace must keep an explicit Back to Intake action for genuine source edits"
);

assert.match(
  workspace,
  /createSpotQuote\(envelopeId, createQuoteRequest\)/,
  "finalized live workspace must use the existing SPOT quote creation path"
);

assert.match(
  workspace,
  /disabled=\{!isReviewLocked \|\| isCreatingQuote \|\| Boolean\(createdQuoteId\)\}/,
  "Create Quote action must require finalized review and block duplicate clicks"
);

assert.match(
  finalReviewPanel,
  /\{!isLive\s*&&\s*\(\s*<div className="flex items-center gap-2 text-xs">/,
  "prototype override checkbox must be wrapped in !isLive"
);

assert.match(
  finalReviewPanel,
  /\{!isLive\s*&&\s*\(\s*<div className="text-center text-xs text-slate-500 mt-2">/,
  "prototype warning footer must be wrapped in !isLive"
);

assert.match(
  finalReviewPanel,
  /disabled=\{\s*isReviewLocked\s*\|\|\s*\(!canFinishReview\s*&&\s*!canUsePrototypeOverride\)\s*\}/,
  "demo override behaviour must remain integrated with finalization button state"
);

console.log("exception workspace routing checks passed");
