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

  console.log("Starting Phase 8D.1 Draft Quote Contract UI Adequacy Checks...");

  // 1. Structure validation
  assert.equal(hardCaseAirImportData.contract_version, "1.0.0");
  assert.ok(Array.isArray(hardCaseAirImportData.suggested_charges));
  assert.equal(hardCaseAirImportData.suggested_charges.length, 5);

  // 2. Validate review queue mapping details
  assert.equal(hardCaseAirImportData.review_queue.length, 3);
  const queueTypes = new Set(hardCaseAirImportData.review_queue.map(q => q.type));
  assert.ok(queueTypes.has("charge_needs_review"));
  assert.ok(queueTypes.has("unclassified_item"));

  // 3. Check similarity groups
  const groupIds = hardCaseAirImportData.suggested_charges
    .map(c => c.similarity_group_id)
    .filter(Boolean);
  assert.ok(groupIds.includes("sim-surcharges"));

  // 4. Verify unclassified item details
  assert.equal(hardCaseAirImportData.unclassified_items.length, 1);
  assert.equal(hardCaseAirImportData.unclassified_items[0].id, "unclass-001");
  assert.ok(hardCaseAirImportData.unclassified_items[0].raw_text.includes("SGD 120.00"));

  console.log("Draft quote contract UI adequacy checks passed successfully!");
}

runTests().catch(err => {
  console.error("Test execution failed:", err);
  process.exit(1);
});
