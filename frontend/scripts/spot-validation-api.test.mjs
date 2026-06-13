import assert from "node:assert/strict";
import ts from "typescript";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());
const helperSourcePath = path.join(frontendRoot, "src", "lib", "api", "spot-validation.ts");

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName,
  }).outputText;
}

// Read and inspect query builder function inside spot-validation.ts
const source = await readFile(helperSourcePath, "utf8");
const transpiled = transpile(source, helperSourcePath);

// Test query string building logic statically or through transpiled mock
// Since fetch is not available globally in node, we mock fetch and test the calls
globalThis.API_BASE_URL = "http://localhost:8000";

let lastFetchUrl = null;
let lastFetchOptions = null;

globalThis.fetch = async (url, options) => {
  lastFetchUrl = url;
  lastFetchOptions = options;
  return {
    ok: true,
    json: async () => ({})
  };
};

// Mock localstorage/authToken resolver
globalThis.localStorage = {
  getItem: (key) => "test-token"
};

// We dynamic import the spot-validation module
const tempHelperModule = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
  }
}).outputText;

// Simple execution environment
const moduleObj = { exports: {} };
const executeFn = new Function("exports", "require", tempHelperModule);
executeFn(moduleObj.exports, (mod) => {
  if (mod === "./shared") {
    return {
      API_BASE_URL: "http://localhost:8000",
      getJson: async (url) => {
        lastFetchUrl = url;
        return {};
      }
    };
  }
  return {};
});

const { getSpotSnapshotMetrics, getSpotComparisonMetrics, getSpotMaintenanceInsights } = moduleObj.exports;

// Test 1: Mappings with empty filters
{
  lastFetchUrl = null;
  await getSpotSnapshotMetrics({});
  assert.equal(lastFetchUrl, "http://localhost:8000/api/v3/spot/template-validation/snapshot-metrics/");
}

// Test 2: Date filters mapping
{
  lastFetchUrl = null;
  await getSpotSnapshotMetrics({ start_date: "2026-06-01", end_date: "2026-06-10" });
  assert.match(lastFetchUrl, /start_date=2026-06-01/);
  assert.match(lastFetchUrl, /end_date=2026-06-10/);
}

// Test 3: Limit and min snapshots mapping
{
  lastFetchUrl = null;
  await getSpotMaintenanceInsights({ limit: 20, min_snapshots: 10 });
  assert.match(lastFetchUrl, /limit=20/);
  assert.match(lastFetchUrl, /min_snapshots=10/);
}

console.log("Spot validation API client unit tests passed successfully.");
