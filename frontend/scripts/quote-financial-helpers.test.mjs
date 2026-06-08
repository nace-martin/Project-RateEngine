import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const helperSourcePath = path.join(frontendRoot, "src", "lib", "quote-financial-helpers.ts");

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
  const tempDir = await mkdtemp(path.join(tmpdir(), "quote-financial-helpers-test-"));
  const libDir = path.join(tempDir, "lib");

  try {
    await mkdir(libDir, { recursive: true });

    const helperSource = await readFile(helperSourcePath, "utf8");

    const helperModule = transpile(helperSource, helperSourcePath)
      .replace(/from ['"]\.\/types['"]/g, "from './types.mjs'");

    await writeFile(path.join(libDir, "quote-financial-helpers.mjs"), helperModule, "utf8");
    await writeFile(path.join(libDir, "types.mjs"), `export {}`, "utf8");

    const helpers = await import(`file://${path.join(libDir, "quote-financial-helpers.mjs")}`);
    return helpers;
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const {
  toMoneyString,
  mapCanonicalComponentToLeg,
  mapCanonicalLineItemToBreakdownLine,
  buildCanonicalTotals,
  formatAmount,
  getBucket,
  calculateBucketTotal,
  readField,
  readStringField,
  getDisplaySellAmount,
  isAvailable,
  displayValue,
  displayApplicable,
  displayMoney,
  displayPercent,
  findRawLine,
  lineWarnings,
  sourceLabel,
} = await loadModules();

// Test: formatting
assert.equal(toMoneyString(12.3456), "12.35");
assert.equal(formatAmount("1234.56", "PGK"), "PGK 1,234.56");
assert.equal(formatAmount(100, "USD"), "USD 100.00");

// Test: display formatting helper
assert.equal(isAvailable(null), false);
assert.equal(isAvailable(undefined), false);
assert.equal(isAvailable(""), false);
assert.equal(isAvailable("POM"), true);

assert.equal(displayValue("POM"), "POM");
assert.equal(displayValue(null), "Not available");

assert.equal(displayApplicable("POM", true), "POM");
assert.equal(displayApplicable("POM", false), "Not applicable");

assert.equal(displayMoney(1234.56, "PGK"), "PGK 1,234.56");
assert.equal(displayMoney(null, "PGK"), "Not available");

assert.equal(displayPercent(12.345), "12.35%");
assert.equal(displayPercent("POM"), "POM");
assert.equal(displayPercent(null), "Not available");

// Test: bucket/leg mapping
assert.equal(mapCanonicalComponentToLeg("ORIGIN_LOCAL"), "ORIGIN");
assert.equal(mapCanonicalComponentToLeg("DESTINATION_LOCAL"), "DESTINATION");
assert.equal(mapCanonicalComponentToLeg("FREIGHT"), "FREIGHT");
assert.equal(mapCanonicalComponentToLeg("UNKNOWN"), "DESTINATION");

assert.equal(getBucket({ leg: "MAIN" }), "FREIGHT");
assert.equal(getBucket({ leg: "FREIGHT" }), "FREIGHT");
assert.equal(getBucket({ leg: "ORIGIN" }), "ORIGIN");
assert.equal(getBucket({ leg: "DESTINATION" }), "DESTINATION");

// Test: calculateBucketTotal
const mockLines = [
  { sell_pgk: "123.45", sell_fcy: "100.00" },
  { sell_pgk: "20.00", sell_fcy: "15.00" }
];
assert.equal(calculateBucketTotal(mockLines, "sell_pgk"), 143.45);
assert.equal(calculateBucketTotal(mockLines, "sell_fcy"), 115.00);

// Test: findRawLine
const rawLines = [
  { id: "line-1", product_code: "POM", description: "Line 1" },
  { id: "line-2", product_code: "LAE", description: "Line 2" }
];
assert.deepEqual(findRawLine(rawLines, { line_id: "line-2" }), rawLines[1]);
assert.deepEqual(findRawLine(rawLines, { product_code: "POM", description: "Line 1" }), rawLines[0]);

// Test: lineWarnings
assert.deepEqual(lineWarnings({}, { is_rate_missing: true }), [{ text: "Missing buy rate", level: "critical" }]);
assert.deepEqual(lineWarnings({ is_manual_override: true }, {}), [{ text: "Manual override", level: "info" }]);
assert.deepEqual(lineWarnings({ rate_source: "FALLBACK_RULE" }, {}), [{ text: "FX or rate fallback applied", level: "info" }]);

// Test: sourceLabel
assert.equal(sourceLabel({ is_spot_sourced: true }, {}), "SPOT");
assert.equal(sourceLabel({}, { is_spot_sourced: true }), "SPOT");
assert.equal(sourceLabel({ is_manual_override: true }, {}), "Manual entry");
assert.equal(sourceLabel({ rate_source: "DB_TARIFF" }, {}), "V4 rate card");
assert.equal(sourceLabel({ rate_source: "FALLBACK_RULE" }, {}), "Fallback rule");

// Test: mapCanonicalLineItemToBreakdownLine
const canonicalItem = {
  component: "ORIGIN_LOCAL",
  product_code: "POM_LOCAL",
  description: "Port Moresby Handling",
  cost_amount: "50.00",
  sell_amount: "100.00",
  tax_amount: "10.00",
  margin_percent: "50",
  cost_currency: "PGK",
  cost_source: "TARIFF",
  included_in_total: true,
};
const mapped = mapCanonicalLineItemToBreakdownLine(canonicalItem, "PGK");
assert.equal(mapped.leg, "ORIGIN");
assert.equal(mapped.sell_pgk, "100.00");
assert.equal(mapped.sell_pgk_incl_gst, "110.00");
assert.equal(mapped.gst_amount, "10.00");

// Test: buildCanonicalTotals
const mockTotalsResult = {
  currency: "USD",
  sell_total: "1100.00",
  tax_breakdown: { gst_amount: "100.00" },
  total_sell_pgk: "3000.00",
};
const totals = buildCanonicalTotals(mockTotalsResult);
assert.equal(totals.currency, "USD");
assert.equal(totals.total_quote_amount, "1100.00");
assert.equal(totals.total_gst, "100.00");
assert.equal(totals.total_sell_ex_gst, "1000.00");

console.log("quote financial helpers checks passed");
