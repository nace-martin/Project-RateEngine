import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const normalizerSourcePath = path.join(frontendRoot, "src", "lib", "draft-quote-normalization.ts");
const workspaceSourcePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");
const apiSourcePath = path.join(frontendRoot, "src", "lib", "api.ts");

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName,
  }).outputText;
}

async function loadNormalizer() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "draft-quote-normalization-test-"));
  const libDir = path.join(tempDir, "lib");

  try {
    await mkdir(libDir, { recursive: true });
    const source = await readFile(normalizerSourcePath, "utf8");
    await writeFile(path.join(libDir, "draft-quote-normalization.mjs"), transpile(source, normalizerSourcePath), "utf8");
    return await import(`file://${path.join(libDir, "draft-quote-normalization.mjs")}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

function baseDraftQuote(overrides = {}) {
  return {
    contract_version: "1",
    quote_summary: "Test draft quote",
    shipment_context: {},
    supplier_context: {},
    freight: {},
    suggested_charges: [
      {
        id: "charge-1",
        status: "suggested",
        display_label: "Fuel",
        raw_label: "Fuel",
        suggested_product_code: "IMP-FUEL",
        product_code_conflict: false,
        bucket: "freight",
        currency: "USD",
        amount: "12.50",
        rate: "1.25",
        unit: "kg",
        calculation_basis: null,
        minimum_charge: "230.00",
        percentage_base: null,
        quantity: "10.5",
        include_in_totals: true,
        conditions: [],
        warnings: [],
        review_reason: null,
        evidence: null,
        similarity_group_id: null,
        correction_actions: [],
      },
    ],
    commercial_terms: [],
    warnings: [],
    unclassified_items: [],
    ignored_items: [],
    totals_validation: {
      math_balances: true,
      currency_consistent: true,
      extracted_total: "12.50",
      calculated_total: "12.50",
      difference: "0.00",
      tolerance: "0.01",
      warnings: [],
    },
    review_queue: [],
    correction_actions: [],
    metadata: {},
    ...overrides,
  };
}

const { normalizeDraftQuotePayload } = await loadNormalizer();

// Numeric strings from Decimal JSON are normalized at the Draft Quote API boundary.
{
  const normalized = normalizeDraftQuotePayload(baseDraftQuote());
  assert.equal(normalized.suggested_charges[0].amount, 12.5);
  assert.equal(normalized.suggested_charges[0].rate, 1.25);
  assert.equal(normalized.suggested_charges[0].minimum_charge, 230);
  assert.equal(normalized.suggested_charges[0].quantity, 10.5);
  assert.equal(normalized.totals_validation.extracted_total, 12.5);
  assert.equal(normalized.totals_validation.calculated_total, 12.5);
  assert.equal(normalized.totals_validation.difference, 0);
  assert.equal(normalized.totals_validation.tolerance, 0.01);
}

// JSON numbers remain numbers and optional null values remain null.
{
  const payload = baseDraftQuote({
    suggested_charges: [
      {
        ...baseDraftQuote().suggested_charges[0],
        amount: 0,
        rate: null,
        minimum_charge: null,
        quantity: null,
      },
    ],
    totals_validation: {
      ...baseDraftQuote().totals_validation,
      extracted_total: null,
      calculated_total: null,
      difference: null,
      tolerance: 0,
    },
  });
  const normalized = normalizeDraftQuotePayload(payload);
  assert.equal(normalized.suggested_charges[0].amount, 0);
  assert.equal(normalized.suggested_charges[0].rate, null);
  assert.equal(normalized.suggested_charges[0].minimum_charge, null);
  assert.equal(normalized.suggested_charges[0].quantity, null);
  assert.equal(normalized.totals_validation.extracted_total, null);
  assert.equal(normalized.totals_validation.calculated_total, null);
  assert.equal(normalized.totals_validation.difference, null);
  assert.equal(normalized.totals_validation.tolerance, 0);
}

// Required commercial amounts must fail visibly; they must not be coerced to zero.
{
  const payload = baseDraftQuote({
    suggested_charges: [
      {
        ...baseDraftQuote().suggested_charges[0],
        amount: "not-a-number",
      },
    ],
  });
  assert.throws(
    () => normalizeDraftQuotePayload(payload),
    /Invalid numeric value for suggested_charges\[0\]\.amount/
  );
}

// The Draft Quote API boundary must normalize before returning to callers.
{
  const apiSource = await readFile(apiSourcePath, "utf8");
  assert.ok(
    apiSource.includes("import { normalizeDraftQuotePayload } from './draft-quote-normalization';"),
    "getDraftQuote must import the Draft Quote numeric normalizer."
  );
  assert.ok(
    apiSource.includes("return normalizeDraftQuotePayload(payload as DraftQuote);"),
    "getDraftQuote must return the normalized Draft Quote payload."
  );
}

// Exception Workspace should render rate text for zero/normalized values rather than using a truthy guard.
{
  const workspaceSource = await readFile(workspaceSourcePath, "utf8");
  assert.ok(
    workspaceSource.includes("charge.rate !== null && charge.rate !== undefined"),
    "ExceptionWorkspace must render zero rates and avoid truthy rate checks."
  );
  assert.ok(
    !workspaceSource.includes("{charge.rate && ` | ${humanizeRate"),
    "ExceptionWorkspace must not use the legacy truthy rate render guard."
  );
}

console.log("draft quote normalization checks passed");
