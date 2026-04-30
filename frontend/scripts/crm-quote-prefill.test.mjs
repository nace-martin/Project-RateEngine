import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const sourcePath = path.join(frontendRoot, "src", "lib", "crm-quote-prefill.ts");

async function loadPrefillModule() {
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: sourcePath,
  }).outputText;

  const tempDir = await mkdtemp(path.join(tmpdir(), "crm-quote-prefill-test-"));
  const modulePath = path.join(tempDir, "crm-quote-prefill.mjs");

  try {
    await writeFile(modulePath, transpiled, "utf8");
    return await import(`file://${modulePath}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const { buildQuotePrefillDefaults, quoteModeFromServiceType } = await loadPrefillModule();

assert.equal(quoteModeFromServiceType("AIR"), "AIR");
assert.equal(quoteModeFromServiceType("air"), "AIR");

for (const serviceType of ["SEA", "CUSTOMS", "DOMESTIC", "MULTIMODAL"]) {
  const prefill = buildQuotePrefillDefaults({
    companyId: "company-1",
    opportunityId: "opportunity-1",
    serviceType,
  });

  assert.equal(
    Object.hasOwn(prefill.defaultValues, "mode"),
    false,
    `${serviceType} should not prefill quote mode`,
  );
  assert.equal(prefill.unsupportedServiceType, serviceType);
}

const airPrefill = buildQuotePrefillDefaults({
  companyId: "company-1",
  opportunityId: "opportunity-1",
  serviceType: "AIR",
});

assert.equal(airPrefill.defaultValues.mode, "AIR");
assert.equal(airPrefill.unsupportedServiceType, undefined);

console.log("crm quote prefill safety checks passed");
