import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());
const spotPagePath = path.join(frontendRoot, "src", "app", "quotes", "spot", "[speId]", "page.tsx");
const livePagePath = path.join(frontendRoot, "src", "app", "quotes", "spot", "[speId]", "exception-workspace", "page.tsx");
const demoPagePath = path.join(frontendRoot, "src", "app", "quotes", "spot", "exception-workspace-demo", "page.tsx");
const workspacePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");

const [spotPage, livePage, demoPage, workspace] = await Promise.all([
  readFile(spotPagePath, "utf8"),
  readFile(livePagePath, "utf8"),
  readFile(demoPagePath, "utf8"),
  readFile(workspacePath, "utf8"),
]);

assert.match(
  spotPage,
  /Review in Exception Workspace/,
  "real SPOT envelope page must expose a live Exception Workspace action",
);

assert.match(
  spotPage,
  /router\.push\(`\/quotes\/spot\/\$\{speId\}\/exception-workspace`\)/,
  "real SPOT envelope action must pass the current envelope ID into the live workspace route",
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
  /<ExceptionWorkspace initialData=\{data\} isLive=\{true\} envelopeId=\{speId\} \/>/,
  "live workspace must pass real payload and envelope ID into the workspace component",
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
  workspace,
  /type: "accept_suggestion"/,
  "live accept-suggestion actions must persist through the Draft Quote resolve API",
);

assert.match(
  workspace,
  /const canUsePrototypeOverride = !isLive && prototypeOverride;/,
  "prototype finalization override must be disabled in live workspace mode",
);

assert.match(
  workspace,
  /\{!isLive\s*&&\s*\(\s*<div className="flex items-center gap-2 text-xs">/,
  "prototype override checkbox must be wrapped in !isLive"
);

assert.match(
  workspace,
  /\{!isLive\s*&&\s*\(\s*<div className="text-center text-xs text-slate-500 mt-2">/,
  "prototype warning footer must be wrapped in !isLive"
);

assert.match(
  workspace,
  /disabled=\{isReviewLocked\s*\|\|\s*\(!canFinishReview\s*&&\s*!canUsePrototypeOverride\)\}/,
  "demo override behaviour must remain integrated with finalization button state"
);

console.log("exception workspace routing checks passed");
