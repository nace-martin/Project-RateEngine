import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const helperSourcePath = path.join(frontendRoot, "src", "lib", "quote-detail-helpers.ts");
const quoteHelpersSourcePath = path.join(frontendRoot, "src", "lib", "quote-helpers.ts");

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
  const tempDir = await mkdtemp(path.join(tmpdir(), "quote-detail-helpers-test-"));
  const libDir = path.join(tempDir, "lib");

  try {
    await mkdir(libDir, { recursive: true });

    const helperSource = await readFile(helperSourcePath, "utf8");
    const quoteHelpersSource = await readFile(quoteHelpersSourcePath, "utf8");

    const helperModule = transpile(helperSource, helperSourcePath)
      .replace(/from ['"]\.\/quote-helpers['"]/g, "from './quote-helpers.mjs'")
      .replace(/from ['"]\.\/types['"]/g, "from './types.mjs'");

    await writeFile(path.join(libDir, "quote-detail-helpers.mjs"), helperModule, "utf8");
    await writeFile(path.join(libDir, "quote-helpers.mjs"), transpile(quoteHelpersSource, quoteHelpersSourcePath), "utf8");
    await writeFile(path.join(libDir, "types.mjs"), `export {}`, "utf8");

    const helpers = await import(`file://${path.join(libDir, "quote-detail-helpers.mjs")}`);
    return helpers;
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const {
  normalizeAirportCode,
  normalizeCountryCode,
  computeShipmentMetrics,
  computeChargeableWeight,
  buildSpotResumeContext,
  buildFxEntries,
} = await loadModules();

// 1. Airport/Country Normalization
{
  assert.equal(normalizeAirportCode("POM"), "POM");
  assert.equal(normalizeAirportCode("POM - Port Moresby"), "POM");
  assert.equal(normalizeAirportCode("  bne  "), "BNE");
  assert.equal(normalizeAirportCode("Invalid Code"), "");
  assert.equal(normalizeAirportCode(null, undefined, "POM"), "POM");

  assert.equal(normalizeCountryCode("PG", "POM"), "PG");
  assert.equal(normalizeCountryCode("AU", "BNE"), "AU");
  assert.equal(normalizeCountryCode(null, "POM"), "PG");
  assert.equal(normalizeCountryCode(null, "BNE"), "AU");
  assert.equal(normalizeCountryCode(null, "XYZ"), "OTHER");
}

// 2. Volumetric vs Actual Chargeable Weight
{
  // Actual weight is higher
  const mockQuote1 = {
    latest_version: {
      payload_json: {
        dimensions: [
          { pieces: 10, length_cm: 10, width_cm: 10, height_cm: 10, gross_weight_kg: 50 },
        ],
      },
    },
  };
  const metrics1 = computeShipmentMetrics(mockQuote1);
  assert.equal(metrics1.pieces, 10);
  assert.equal(metrics1.totalWeightKg, 500); // 10 * 50
  assert.equal(metrics1.chargeableWeightKg, 500); // Actual weight takes precedence

  // Volumetric weight is higher
  const mockQuote2 = {
    latest_version: {
      payload_json: {
        dimensions: [
          { pieces: 10, length_cm: 60, width_cm: 60, height_cm: 60, gross_weight_kg: 5 },
        ],
      },
    },
  };
  const metrics2 = computeShipmentMetrics(mockQuote2);
  assert.equal(metrics2.pieces, 10);
  assert.equal(metrics2.totalWeightKg, 50); // 10 * 5
  assert.equal(metrics2.volumetricWeightKg, 360); // (60*60*60/6000) * 10 = 360
  assert.equal(metrics2.chargeableWeightKg, 360); // Volumetric weight takes precedence
}

// 3. Missing or Malformed Dimensions Fallbacks
{
  const mockQuote = {
    latest_version: {
      total_weight_kg: 80,
      payload_json: {
        total_weight_kg: 100,
        dimensions: [],
      },
    },
  };
  const metrics = computeShipmentMetrics(mockQuote);
  assert.equal(metrics.pieces, 0);
  assert.equal(metrics.totalWeightKg, 100); // payload total_weight_kg preferred over version
  assert.equal(metrics.chargeableWeightKg, 100);

  const mockQuoteFallback = {
    latest_version: {
      total_weight_kg: 150,
      payload_json: {},
    },
  };
  const metricsFallback = computeShipmentMetrics(mockQuoteFallback);
  assert.equal(metricsFallback.totalWeightKg, 150); // falls back to version total_weight_kg
  assert.equal(metricsFallback.chargeableWeightKg, 150);
}

// 4. FX Entries
{
  const mockQuote = {
    output_currency: "USD",
    latest_version: {
      totals: { currency: "USD" },
      lines: [],
    },
  };
  const mockCompute = {
    totals: { currency: "USD" },
    exchange_rates: { "USD/PGK": "3.55" },
  };

  const fx = buildFxEntries(mockQuote, mockCompute);
  assert.deepEqual(fx, [["USD/PGK", "3.55"]]);
}

// 5. FX Fallback from Line Items when explicit exchange rates are missing
{
  const mockQuote = {
    output_currency: "AUD",
    latest_version: {
      totals: { currency: "AUD" },
      lines: [
        { sell_fcy_currency: "AUD", exchange_rate: 2.45 },
      ],
    },
  };
  const fx = buildFxEntries(mockQuote, null);
  assert.deepEqual(fx, [["AUD/PGK", "2.45"]]);
}

// 6. SPOT Resume Context
{
  const mockQuote = {
    id: "quote-spot",
    quote_number: "Q-123",
    customer: { id: "cust-1", company_name: "Test Corp" },
    service_scope: "D2D",
    payment_term: "COLLECT",
    output_currency: "USD",
    shipment_type: "EXPORT",
    origin_location: "POM - Port Moresby",
    destination_location: "BNE - Brisbane",
    latest_version: {
      payload_json: {
        origin_airport: "POM",
        destination_airport: "BNE",
        origin_country: "PG",
        destination_country: "AU",
        commodity_code: "CRG",
        dimensions: [
          { pieces: 2, length_cm: 20, width_cm: 20, height_cm: 20, gross_weight_kg: 10 },
        ],
      },
    },
    request_details_json: {
      customer_id: "cust-1",
    },
  };

  const context = buildSpotResumeContext(mockQuote);
  assert.equal(context.originCode, "POM");
  assert.equal(context.destinationCode, "BNE");
  assert.equal(context.originCountry, "PG");
  assert.equal(context.destinationCountry, "AU");
  assert.equal(context.commodity, "CRG");
  assert.equal(context.serviceScope, "D2D");
  assert.equal(context.paymentTerm, "COLLECT");
  assert.equal(context.pieces, 2);
  assert.equal(context.chargeableWeight, 20); // ceil(20 kg actual)
  assert.equal(context.customerId, "cust-1");
  assert.equal(context.customerName, "Test Corp");
}

console.log("quote detail helpers checks passed");
