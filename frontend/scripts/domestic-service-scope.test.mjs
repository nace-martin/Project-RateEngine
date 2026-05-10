import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const sourcePath = path.join(frontendRoot, "src", "lib", "domestic-service-scope.ts");

async function loadModule() {
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: sourcePath,
  }).outputText;

  const tempDir = await mkdtemp(path.join(tmpdir(), "domestic-service-scope-test-"));
  const modulePath = path.join(tempDir, "domestic-service-scope.mjs");

  try {
    await writeFile(modulePath, transpiled, "utf8");
    return await import(`file://${modulePath}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const {
  getDomesticServiceScopeError,
  isDomesticServiceScopeAvailable,
  resolveCountryCode,
} = await loadModule();

assert.equal(resolveCountryCode(null, "HGU"), "PG");
assert.equal(resolveCountryCode({ code: "BNE", display_name: "Brisbane (BNE), AU" }, "BNE"), "AU");

assert.match(
  getDomesticServiceScopeError("D2D", "POM", "HGU", "PG", "PG"),
  /Delivery is only available/,
);
assert.match(
  getDomesticServiceScopeError("D2D", "POM", "HGU", "pg", "pg"),
  /Delivery is only available/,
);
assert.equal(isDomesticServiceScopeAvailable("D2A", "POM", "HGU", "PG", "PG"), true);
assert.equal(isDomesticServiceScopeAvailable("A2D", "HGU", "POM", "PG", "PG"), true);
assert.equal(isDomesticServiceScopeAvailable("A2A", "HGU", "GKA", "PG", "PG"), true);
assert.match(
  getDomesticServiceScopeError("D2A", "HGU", "POM", "PG", "PG"),
  /Pickup is only available/,
);
assert.match(
  getDomesticServiceScopeError("A2D", "POM", "HGU", "PG", "PG"),
  /Delivery is only available/,
);
assert.match(
  getDomesticServiceScopeError("D2D", "POM", "WEW", "PG", "PG"),
  /Delivery is only available/,
);
assert.equal(getDomesticServiceScopeError("A2D", "BNE", "HGU", "AU", "PG"), "");

console.log("domestic service scope checks passed");
