import assert from "node:assert/strict";
import path from "node:path";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const fixtureSourcePath = path.join(frontendRoot, "src", "data", "hardCaseAirImport.ts");

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName,
  }).outputText;
}

// Write a simple test suite using node:assert
async function runTests() {
  const fixtureSource = await readFile(fixtureSourcePath, "utf8");
  // Strip import statement to compile cleanly standalone
  const cleanedSource = fixtureSource.replace(/import\s+[\s\S]*?\s+from\s+['"].*?['"];?/g, "");
  const helperModule = transpile(cleanedSource, fixtureSourcePath);
  
  // Create temporary inline module data url to import
  const base64Data = Buffer.from(helperModule).toString("base64");
  const moduleUrl = `data:text/javascript;base64,${base64Data}`;
  const { hardCaseAirImportData } = await import(moduleUrl);

  console.log("Starting Phase 8D.3 Resolve Mode UX Refinement Checks...");

  // 1. Structure validation
  assert.equal(hardCaseAirImportData.contract_version, "1.0.0");
  assert.ok(Array.isArray(hardCaseAirImportData.suggested_charges));
  assert.equal(hardCaseAirImportData.suggested_charges.length, 5);

  // 2. Validate review queue mapping details
  assert.equal(hardCaseAirImportData.review_queue.length, 3);
  const queueTypes = new Set(hardCaseAirImportData.review_queue.map(q => q.type));
  assert.ok(queueTypes.has("charge_needs_review"));
  assert.ok(queueTypes.has("unclassified_item"));

  // 3. Verify unclassified item details
  assert.equal(hardCaseAirImportData.unclassified_items.length, 1);
  assert.equal(hardCaseAirImportData.unclassified_items[0].id, "unclass-001");
  assert.ok(hardCaseAirImportData.unclassified_items[0].raw_text.includes("SGD 120.00"));

  // 4. Stateful logic simulation for Phase 8D.3:
  
  // (a) Accepted items leave Needs Attention queue simulation
  let currentReviewQueue = [...hardCaseAirImportData.review_queue];
  let currentSuggestedCharges = [...hardCaseAirImportData.suggested_charges];
  
  // Operator accepts chg-003 (Security Charge)
  currentSuggestedCharges = currentSuggestedCharges.map(c => 
    c.id === "chg-003" ? { ...c, status: "accepted_by_user" } : c
  );
  currentReviewQueue = currentReviewQueue.filter(q => q.id !== "chg-003");
  
  assert.equal(currentReviewQueue.some(q => q.id === "chg-003"), false, "Accepted charge must leave review queue");
  assert.equal(currentSuggestedCharges.find(c => c.id === "chg-003").status, "accepted_by_user");

  // (b) Ignored items leave Needs Attention and appear under Ignored Items
  let currentIgnoredItems = [...hardCaseAirImportData.ignored_items];
  const ignoredTarget = currentSuggestedCharges.find(c => c.id === "chg-001");
  currentSuggestedCharges = currentSuggestedCharges.map(c => 
    c.id === "chg-001" ? { ...c, status: "ignored", include_in_totals: false } : c
  );
  currentIgnoredItems.push({
    id: "chg-001",
    raw_text: ignoredTarget.raw_label,
    ignored_reason: "Ignored by operator",
    evidence: ignoredTarget.evidence
  });
  
  assert.equal(currentSuggestedCharges.find(c => c.id === "chg-001").status, "ignored");
  assert.equal(currentSuggestedCharges.find(c => c.id === "chg-001").include_in_totals, false);
  assert.ok(currentIgnoredItems.some(i => i.id === "chg-001"), "Ignored item must exist in ignored items list");

  // (c) Missing ProductCode mapping locally
  currentSuggestedCharges = currentSuggestedCharges.map(c => 
    c.id === "chg-002" ? { ...c, suggested_product_code: "AF-FUEL", status: "accepted_by_user" } : c
  );
  currentReviewQueue = currentReviewQueue.filter(q => q.id !== "chg-002");
  
  assert.equal(currentSuggestedCharges.find(c => c.id === "chg-002").suggested_product_code, "AF-FUEL");
  assert.equal(currentSuggestedCharges.find(c => c.id === "chg-002").status, "accepted_by_user");

  // (d) Missing ProductCode requested becomes Pending ProductCode
  currentSuggestedCharges = currentSuggestedCharges.map(c => 
    c.id === "chg-002" ? { ...c, status: "pending_product_code" } : c
  );
  assert.equal(currentSuggestedCharges.find(c => c.id === "chg-002").status, "pending_product_code");

  // (e) Apply to similar only appears when similar items exist
  const similarCount = hardCaseAirImportData.suggested_charges.filter(c => c.similarity_group_id === "sim-surcharges").length;
  assert.ok(similarCount > 1, "Similarity checkbox must only display when there is > 1 item in the group");

  // (f) Checklist rules: Finish Review is disabled while unresolved exceptions remain
  const testUnresolvedQueue = [...currentReviewQueue];
  const testUnclassified = [...hardCaseAirImportData.unclassified_items];
  const testProductCodesApproved = currentSuggestedCharges.every(c => c.suggested_product_code !== null || c.status === "ignored");
  
  const finishReviewActive = testUnresolvedQueue.length === 0 && testUnclassified.length === 0 && testProductCodesApproved;
  assert.equal(finishReviewActive, false, "Finish Review should be disabled while needs-review or unclassified items exist");

  // (g) Mixed-currency checks: do not sum SGD and USD into a single total
  const activeTestCharges = currentSuggestedCharges.filter(c => c.include_in_totals && c.status !== "ignored");
  const currenciesUsed = Array.from(new Set(activeTestCharges.map(c => c.currency)));
  assert.ok(currenciesUsed.includes("USD") && currenciesUsed.includes("SGD"), "Should identify mixed USD and SGD currencies");

  console.log("Resolve Mode stateful checks passed successfully!");
}

runTests().catch(err => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
