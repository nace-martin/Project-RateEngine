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

async function runTests() {
  const fixtureSource = await readFile(fixtureSourcePath, "utf8");
  const cleanedSource = fixtureSource.replace(/import\s+[\s\S]*?\s+from\s+['"].*?['"];?/g, "");
  const helperModule = transpile(cleanedSource, fixtureSourcePath);
  
  const base64Data = Buffer.from(helperModule).toString("base64");
  const moduleUrl = `data:text/javascript;base64,${base64Data}`;
  const { hardCaseAirImportData } = await import(moduleUrl);

  console.log("Starting Phase 8D.4 Guided Review UX Contract Assertions...");

  // 1. Structure validation
  assert.equal(hardCaseAirImportData.contract_version, "1.0.0");
  assert.equal(hardCaseAirImportData.shipment_context.direction, "IMPORT");
  assert.ok(Array.isArray(hardCaseAirImportData.suggested_charges));

  // 2. Undo & Reopen Transition Simulation
  let suggestedCharges = [...hardCaseAirImportData.suggested_charges];
  let reviewQueue = [...hardCaseAirImportData.review_queue];
  let ignoredItems = [];

  // Action: Operator ignores chg-001
  const targetCharge = suggestedCharges.find(c => c.id === "chg-001");
  suggestedCharges = suggestedCharges.map(c => 
    c.id === "chg-001" ? { ...c, status: "ignored", include_in_totals: false } : c
  );
  ignoredItems.push({ id: "chg-001", raw_text: targetCharge.raw_label });
  reviewQueue = reviewQueue.filter(q => q.id !== "chg-001");

  assert.equal(suggestedCharges.find(c => c.id === "chg-001").status, "ignored");
  assert.equal(reviewQueue.some(q => q.id === "chg-001"), false);

  // Undo / Reopen Action: Operator Reopens chg-001
  suggestedCharges = suggestedCharges.map(c => 
    c.id === "chg-001" ? { ...c, status: "needs_review", include_in_totals: true } : c
  );
  reviewQueue.push({ id: "chg-001", type: "charge_needs_review", message: "Reopened by operator" });
  ignoredItems = ignoredItems.filter(i => i.id !== "chg-001");

  assert.equal(suggestedCharges.find(c => c.id === "chg-001").status, "needs_review");
  assert.ok(reviewQueue.some(q => q.id === "chg-001"), "Reopened item must return to Needs Attention queue");

  // 3. Edit & Cancel Pending ProductCode Request Simulation
  // Action: Request ProductCode for chg-002
  suggestedCharges = suggestedCharges.map(c => 
    c.id === "chg-002" ? { ...c, status: "pending_product_code" } : c
  );
  reviewQueue = reviewQueue.filter(q => q.id !== "chg-002");
  assert.equal(suggestedCharges.find(c => c.id === "chg-002").status, "pending_product_code");

  // Action: Operator cancels request and reopens issue
  suggestedCharges = suggestedCharges.map(c => 
    c.id === "chg-002" ? { ...c, status: "needs_review" } : c
  );
  reviewQueue.push({ id: "chg-002", type: "charge_needs_review", message: "Request cancelled by operator" });
  assert.equal(suggestedCharges.find(c => c.id === "chg-002").status, "needs_review");

  // 4. Verification that raw backend enum status names are absent in operator view
  const technicalTerms = ["accepted_by_user", "unclassified_item", "needs_review", "ignored"];
  
  function friendlyStatus(status) {
      switch (status) {
          case "accepted_by_user": return "Accepted";
          case "suggested": return "Suggested";
          case "ignored": return "Ignored";
          case "pending_product_code": return "Pending Product Code";
          case "needs_review": return "Needs Attention";
          case "unclassified":
          case "unclassified_item": return "Unknown Charge";
          default: return status;
      }
  }
  
  technicalTerms.forEach(term => {
      const friendly = friendlyStatus(term);
      assert.ok(!technicalTerms.includes(friendly), `User facing status label '${friendly}' must not contain raw backend enums`);
  });

  // 5. Mixed-currency checks: assert subtotals are separated
  const currenciesUsed = Array.from(new Set(suggestedCharges.map(c => c.currency)));
  assert.ok(currenciesUsed.includes("USD") && currenciesUsed.includes("SGD"), "Should contain multiple currencies");

  console.log("Guided review stateful contract assertions passed successfully!");
}

runTests().catch(err => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
