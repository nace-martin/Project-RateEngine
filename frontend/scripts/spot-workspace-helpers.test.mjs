import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const helperSourcePath = path.join(frontendRoot, "src", "lib", "spot-workspace-helpers.ts");

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName,
  }).outputText;
}

async function loadModules() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "spot-workspace-helpers-test-"));
  const libDir = path.join(tempDir, "lib");

  try {
    await mkdir(libDir, { recursive: true });

    const helperSource = await readFile(helperSourcePath, "utf8");

    const helperModule = transpile(helperSource, helperSourcePath);

    await writeFile(path.join(libDir, "spot-workspace-helpers.mjs"), helperModule, "utf8");

    const helpers = await import(`file://${path.join(libDir, "spot-workspace-helpers.mjs")}`);
    return helpers;
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const {
  isBuySideCharge,
  isStandardRateCharge,
  componentToBucket,
  sanitizeSummaryMessage,
  normalizeSummaryMessage,
  getAnalysisSignalCount,
  normalizeIssueLabel,
  isCountOnlySummaryWarning,
  parseLineIssueWarning,
  getPrimaryIssueKind,
  getIssueProblemMessage,
  humanizeEnum,
  formatProductCodeSummary,
  getChargeStatusLabel,
  chargeUnitLabel,
  formatChargeAmount,
  isActionableAiWarning,
  getSourceSummaryTitle,
  getSourceSummarySubtitle,
  formatMissingComponents,
  formatListWithAnd,
  humanizeRate,
  friendlyStatus,
} = await loadModules();

// 1. humanizeEnum
{
  assert.equal(humanizeEnum("PREPAID"), "Prepaid");
  assert.equal(humanizeEnum("MANUAL_RESOLUTION"), "Manual Resolution");
  assert.equal(humanizeEnum(""), "Not recorded");
  assert.equal(humanizeEnum(null), "Not recorded");
  assert.equal(humanizeEnum("  "), "Not recorded");
  assert.equal(humanizeEnum("COLLECT_"), "Collect");
}

// 2. getPrimaryIssueKind & getIssueProblemMessage
{
  assert.equal(getPrimaryIssueKind(["lowConfidence", "unmapped"]), "unmapped");
  assert.equal(getPrimaryIssueKind(["conditional", "ambiguous"]), "ambiguous");
  assert.equal(getPrimaryIssueKind(["conditional"]), "conditional");

  assert.equal(getIssueProblemMessage(["unmapped"]), "Choose the correct ProductCode before creating the quote.");
  assert.equal(getIssueProblemMessage(["ambiguous"]), "Multiple ProductCodes matched. Confirm the correct one.");
  assert.equal(getIssueProblemMessage(["lowConfidence"]), "Check the normalized charge label before confirming.");
  assert.equal(getIssueProblemMessage(["conditional"]), "Confirm whether this conditional charge should stay in the quote.");
}

// 3. normalizeSummaryMessage
{
  assert.equal(normalizeSummaryMessage("AI: hello"), "hello");
  assert.equal(normalizeSummaryMessage("AI critic flagged possible missed charges: cogs"), "Possible missed charges: cogs");
  assert.equal(normalizeSummaryMessage("AI critic flagged possible hallucinations: cogs"), "Please verify these charges: cogs");
  assert.equal(normalizeSummaryMessage("AI returned unmapped charges requiring manual review: fuel"), "Some imported charges need manual review: fuel");
  assert.equal(normalizeSummaryMessage("AI analysis failed: error"), "Import check failed: error");
  assert.equal(normalizeSummaryMessage("AI analysis is missing required rate or currency fields"), "Some imported lines are missing rate or currency details.");
  assert.equal(normalizeSummaryMessage("Line 12: Low-confidence normalization for label"), "Line 12: Please verify the charge label for label");
}

// 4. isCountOnlySummaryWarning
{
  assert.equal(isCountOnlySummaryWarning("1 extracted charge(s) could not be mapped cleanly."), true);
  assert.equal(isCountOnlySummaryWarning("3 extracted charge line(s) were low-confidence."), true);
  assert.equal(isCountOnlySummaryWarning("Some imported charges need manual review: "), true);
  assert.equal(isCountOnlySummaryWarning("Line 12: Error occurred"), true);
  assert.equal(isCountOnlySummaryWarning("This is an actual warning"), false);
}

// 5. parseLineIssueWarning
{
  const lcWarning = "Line 5: Low-confidence normalization for 'Fuel Surcharge'";
  const lcResult = parseLineIssueWarning(lcWarning);
  assert.deepEqual(lcResult.labels, ["Fuel Surcharge"]);
  assert.equal(lcResult.kind, "lowConfidence");

  const unmappedWarning = "Line 7: Unmapped charge 'Security Charge'";
  const unmappedResult = parseLineIssueWarning(unmappedWarning);
  assert.deepEqual(unmappedResult.labels, ["Security Charge"]);
  assert.equal(unmappedResult.kind, "unmapped");

  const manualWarning = "Some imported charges need manual review: Handling Fee, Delivery Charge";
  const manualResult = parseLineIssueWarning(manualWarning);
  assert.deepEqual(manualResult.labels, ["Handling Fee", "Delivery Charge"]);
  assert.equal(manualResult.kind, "unmapped");

  assert.equal(parseLineIssueWarning("Random non-issue message"), null);
}

// 6. getChargeStatusLabel
{
  assert.equal(getChargeStatusLabel({ manual_resolution_status: "RESOLVED" }), "Manually resolved");
  assert.equal(getChargeStatusLabel({ normalization_status: "MATCHED" }), "Matched");
  assert.equal(getChargeStatusLabel({ normalization_status: "AMBIGUOUS" }), "Ambiguous");
  assert.equal(getChargeStatusLabel({ normalization_status: "UNMAPPED" }), "Needs review");
  assert.equal(getChargeStatusLabel({}), "Not normalized");
}

// 7. formatChargeAmount
{
  assert.equal(formatChargeAmount({ amount: 150, currency: "PGK" }), "150 PGK");
  assert.equal(formatChargeAmount({ amount: " 250.50 ", currency: "USD" }), "250.50 USD");
  assert.equal(formatChargeAmount({ currency: "AUD" }), "AUD");
  assert.equal(formatChargeAmount({}), "");
}

// 8. getSourceSummaryTitle & getSourceSummarySubtitle
{
  assert.equal(getSourceSummaryTitle("Unified Intake", "mixed"), "Uploaded rates");
  assert.equal(getSourceSummaryTitle("AI Agent Reply", "airfreight"), "Agent Reply");
  assert.equal(getSourceSummaryTitle("", "origin_charges"), "Origin Charges import");

  assert.equal(getSourceSummarySubtitle("mixed"), "Imported lines are grouped for this quote");
  assert.equal(getSourceSummarySubtitle("destination_charges"), "Destination Charges lines are grouped for this quote");
}

// 9. formatMissingComponents & formatListWithAnd
{
  assert.deepEqual(formatMissingComponents(["DESTINATION_LOCAL", "FREIGHT"]), ["Destination Charges", "Freight Rate"]);
  assert.deepEqual(formatMissingComponents([]), null);
  assert.deepEqual(formatMissingComponents(null), null);

  assert.equal(formatListWithAnd(["One"]), "One");
  assert.equal(formatListWithAnd(["One", "Two"]), "One and Two");
  assert.equal(formatListWithAnd(["One", "Two", "Three"]), "One, Two, and Three");
}

// 10. humanizeRate
{
  assert.equal(humanizeRate(230, "kg", "...Min..."), "Minimum USD 230.00 or USD 230.00 per kg");
  assert.equal(humanizeRate(0, "kg", "Fuel"), "Flat fee");
  assert.equal(humanizeRate(null, null, "..."), "Flat fee");
  assert.equal(humanizeRate(1.23, "set", "Handling"), "SGD 1.23 per set");
  assert.equal(humanizeRate("1.23", "set", "Handling"), "SGD 1.23 per set");
  assert.equal(humanizeRate("not-a-number", "kg", "Fuel"), "Rate unavailable");
  assert.equal(humanizeRate(1.5, "kg", "Fuel"), "USD 1.50 per kg");
  assert.equal(humanizeRate(0.85, "kg", "Security"), "USD 0.85 per kg");
  assert.equal(humanizeRate(5.00, "unit", "Freight"), "5.00 per unit");
}

// 11. friendlyStatus
{
  assert.equal(friendlyStatus("accepted_by_user"), "Accepted");
  assert.equal(friendlyStatus("suggested"), "Suggested");
  assert.equal(friendlyStatus("ignored"), "Ignored");
  assert.equal(friendlyStatus("pending_product_code"), "Pending Product Code");
  assert.equal(friendlyStatus("needs_review"), "Needs Attention");
  assert.equal(friendlyStatus("unclassified"), "Unknown Charge");
  assert.equal(friendlyStatus("unclassified_item"), "Unknown Charge");
  assert.equal(friendlyStatus("unknown_status"), "unknown_status");
}

console.log("spot workspace helpers checks passed");
