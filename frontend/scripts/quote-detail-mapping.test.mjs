import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const sourcePath = path.join(frontendRoot, "src", "lib", "quote-detail-mapping.ts");

async function loadModule() {
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: sourcePath,
  }).outputText;

  const tempDir = await mkdtemp(path.join(tmpdir(), "quote-detail-mapping-test-"));
  const modulePath = path.join(tempDir, "quote-detail-mapping.mjs");

  try {
    await writeFile(modulePath, transpiled, "utf8");
    return await import(`file://${modulePath}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

function serviceComponent(overrides = {}) {
  return {
    id: "component-1",
    code: "FREIGHT",
    description: "Air Freight",
    category: "FREIGHT",
    unit: "KG",
    leg: "MAIN",
    ...overrides,
  };
}

function line(overrides = {}) {
  return {
    id: "line-1",
    service_component: serviceComponent(),
    component: "FREIGHT",
    product_code: "AIR_FREIGHT",
    description: "Air Freight",
    cost_pgk: "180.00",
    cost_fcy: "50.00",
    cost_fcy_currency: "USD",
    sell_pgk: "300.00",
    sell_pgk_incl_gst: "330.00",
    sell_fcy: "100.00",
    sell_fcy_incl_gst: "110.00",
    sell_fcy_currency: "USD",
    exchange_rate: "3.0000",
    cost_source: "rate_card",
    cost_source_description: "Rate card freight",
    is_rate_missing: false,
    ...overrides,
  };
}

function totals(overrides = {}) {
  return {
    currency: "USD",
    total_cost_pgk: "180.00",
    total_sell_pgk: "300.00",
    total_sell_pgk_incl_gst: "330.00",
    total_sell_fcy: "100.00",
    total_sell_fcy_incl_gst: "110.00",
    total_sell_fcy_currency: "USD",
    has_missing_rates: false,
    notes: null,
    ...overrides,
  };
}

function latestVersion(overrides = {}) {
  return {
    id: "version-1",
    version_number: 1,
    status: "DRAFT",
    created_at: "2026-06-01T00:00:00Z",
    lines: [line()],
    totals: totals(),
    ...overrides,
  };
}

function canonicalQuoteResult(overrides = {}) {
  return {
    quote_id: "canonical-quote-id",
    status: "DRAFT",
    customer_name: "Acme PNG",
    service_scope: "D2D",
    mode: "AIR",
    origin: "BNE",
    destination: "POM",
    incoterm: "EXW",
    cargo_type: "General Cargo",
    pieces: 1,
    actual_weight: "20.00",
    volumetric_weight: "1.00",
    chargeable_weight: "20.00",
    dimensions_summary: "1 x Box",
    line_items: [],
    currency: "USD",
    sell_total: "110.00",
    total_cost_pgk: "180.00",
    total_sell_pgk: "330.00",
    margin_amount: "120.00",
    margin_percent: "40.00",
    fx_applied: {
      applied: true,
      rate: "3.0000",
      source: "rate_card",
      snapshot_date: "2026-06-01",
      caf_percent: null,
      currency: "USD",
    },
    tax_breakdown: {
      gst_percent: "10.00",
      gst_amount: "10.00",
      tax_basis: "SELL",
      by_code: { GST: "10.00" },
    },
    warnings: ["canonical warning"],
    missing_components: [],
    spot_required: false,
    engine_name: "PricingServiceV4Adapter",
    calculated_at: "2026-06-01T01:00:00Z",
    quote_version: 1,
    ...overrides,
  };
}

function quoteDetail(overrides = {}) {
  return {
    id: "quote-id",
    quote_number: "QT-0001",
    customer: "Acme PNG",
    contact: "Ops Contact",
    mode: "AIR",
    shipment_type: "IMPORT",
    incoterm: "EXW",
    payment_term: "COLLECT",
    service_scope: "D2D",
    output_currency: "USD",
    origin_location: "BNE",
    destination_location: "POM",
    status: "DRAFT",
    valid_until: "2026-06-30",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T02:00:00Z",
    latest_version: latestVersion(),
    quote_result: null,
    ...overrides,
  };
}

const { mapQuoteDetailToComputeResult } = await loadModule();

{
  const canonical = canonicalQuoteResult();
  const mapped = mapQuoteDetailToComputeResult(quoteDetail({ quote_result: canonical }));

  assert.equal(mapped.quote_result, canonical, "canonical quote_result should be preserved by reference");
  assert.equal(mapped.quote_id, "canonical-quote-id");
  assert.equal(mapped.totals.currency, "USD");
  assert.equal(mapped.computation_date, "2026-06-01T01:00:00Z");
  assert.deepEqual(mapped.notes, ["canonical warning"]);
}

{
  const mapped = mapQuoteDetailToComputeResult(quoteDetail());

  assert.equal(mapped.quote_id, "quote-id");
  assert.equal(mapped.sell_lines.length, 1);
  assert.equal(mapped.sell_lines[0].component, "AIR_FREIGHT");
  assert.equal(mapped.sell_lines[0].description, "Air Freight");
  assert.equal(mapped.sell_lines[0].leg, "MAIN");
  assert.equal(mapped.sell_lines[0].gst_amount, "10.00");
  assert.equal(mapped.totals.total_quote_amount, "110.00");
  assert.equal(mapped.totals.cost_pgk, "180.00");
  assert.equal(mapped.exchange_rates["USD/PGK"], "3.0000");
  assert.equal(mapped.quote_result, null);
}

{
  const mapped = mapQuoteDetailToComputeResult(
    quoteDetail({
      output_currency: "USD",
      latest_version: latestVersion({
        totals: totals({
          currency: "USD",
          total_sell_pgk: "450.00",
          total_sell_pgk_incl_gst: "495.00",
          total_sell_fcy: "150.00",
          total_sell_fcy_incl_gst: "165.00",
          total_sell_fcy_currency: "USD",
        }),
        lines: [
          line({
            sell_pgk: "450.00",
            sell_pgk_incl_gst: "495.00",
            sell_fcy: "150.00",
            sell_fcy_incl_gst: "165.00",
            sell_fcy_currency: "USD",
          }),
        ],
      }),
    }),
  );

  assert.equal(mapped.totals.currency, "USD");
  assert.equal(mapped.totals.total_sell_fcy, "150.00");
  assert.equal(mapped.totals.total_sell_fcy_incl_gst, "165.00");
  assert.equal(mapped.totals.total_quote_amount, "165.00");
  assert.equal(mapped.sell_lines[0].sell_currency, "USD");
}

{
  const canonical = canonicalQuoteResult({
    warnings: ["Missing buy rate for AIR_FREIGHT"],
    missing_components: ["AIR_FREIGHT"],
  });
  const mapped = mapQuoteDetailToComputeResult(
    quoteDetail({
      quote_result: canonical,
      latest_version: latestVersion({
        lines: [line({ is_rate_missing: true })],
        totals: totals({
          has_missing_rates: true,
          notes: "Missing buy rate for AIR_FREIGHT",
        }),
      }),
    }),
  );

  assert.deepEqual(mapped.notes, ["Missing buy rate for AIR_FREIGHT"]);
  assert.deepEqual(mapped.quote_result.missing_components, ["AIR_FREIGHT"]);
}

{
  const mapped = mapQuoteDetailToComputeResult(
    quoteDetail({
      output_currency: "PGK",
      latest_version: latestVersion({
        totals: totals({
          currency: "PGK",
          total_cost_pgk: "90.00",
          total_sell_pgk: "200.00",
          total_sell_pgk_incl_gst: "220.00",
          total_sell_fcy: "200.00",
          total_sell_fcy_incl_gst: "220.00",
          total_sell_fcy_currency: "PGK",
        }),
        lines: [
          line({
            cost_pgk: "90.00",
            cost_fcy_currency: "PGK",
            sell_pgk: "200.00",
            sell_pgk_incl_gst: "220.00",
            sell_fcy: "200.00",
            sell_fcy_incl_gst: "220.00",
            sell_fcy_currency: "PGK",
            exchange_rate: null,
          }),
        ],
      }),
    }),
  );

  assert.equal(mapped.totals.currency, "PGK");
  assert.equal(mapped.totals.sell_pgk, "200.00");
  assert.equal(mapped.totals.sell_pgk_incl_gst, "220.00");
  assert.equal(mapped.totals.total_quote_amount, "220.00");
  assert.equal(mapped.sell_lines[0].sell_currency, "PGK");
  assert.deepEqual(mapped.exchange_rates, {});
}

console.log("quote detail mapping checks passed");
