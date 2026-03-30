import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const workflowSourcePath = path.join(frontendRoot, "src", "lib", "quote-workflow.ts");

const expectedMappings = {
  "General Cargo": "GCR",
  "Dangerous Goods": "DG",
  "Perishable / Cold Chain": "PER",
  "Live Animals": "AVI",
  "Valuable / High-Value": "HVC",
  "Oversized / OOG": "OOG",
};

async function loadWorkflowModule() {
  const source = await readFile(workflowSourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: workflowSourcePath,
  }).outputText;

  const tempDir = await mkdtemp(path.join(tmpdir(), "quote-workflow-test-"));
  const modulePath = path.join(tempDir, "quote-workflow.mjs");

  try {
    await writeFile(modulePath, transpiled, "utf8");
    return await import(`file://${modulePath}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

function buildFormData(cargoType) {
  return {
    customer_id: "customer-1",
    contact_id: "contact-1",
    mode: "AIR",
    incoterm: "EXW",
    payment_term: "PREPAID",
    service_scope: "A2A",
    origin_location_id: "origin-1",
    destination_location_id: "destination-1",
    dimensions: [
      {
        pieces: 1,
        length_cm: "10",
        width_cm: "10",
        height_cm: "10",
        gross_weight_kg: "5",
        package_type: "Box",
      },
    ],
    cargo_type: cargoType,
  };
}

const { CARGO_TYPE_TO_COMMODITY_CODE, getCargoTypeForCommodityCode, buildQuoteComputePayload } =
  await loadWorkflowModule();

assert.deepEqual(CARGO_TYPE_TO_COMMODITY_CODE, expectedMappings);

for (const [cargoType, commodityCode] of Object.entries(expectedMappings)) {
  const hydratedCargoType = getCargoTypeForCommodityCode(
    commodityCode,
    commodityCode === "DG",
  );
  assert.equal(
    hydratedCargoType,
    cargoType,
    `expected ${commodityCode} to hydrate to ${cargoType}`,
  );

  const recomputePayload = buildQuoteComputePayload(buildFormData(hydratedCargoType));
  assert.equal(
    recomputePayload.commodity_code,
    commodityCode,
    `expected ${cargoType} to recompute back to ${commodityCode}`,
  );
  assert.equal(
    recomputePayload.is_dangerous_goods,
    commodityCode === "DG",
    `expected dangerous goods flag to stay aligned for ${commodityCode}`,
  );
}

console.log("quote-workflow commodity round-trip checks passed");
