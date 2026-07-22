import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const domainSourcePath = path.join(frontendRoot, "src", "lib", "draft-quote-domain.ts");
const workflowSourcePath = path.join(frontendRoot, "src", "components", "spot", "workspace", "useSpotResolutionWorkflow.ts");

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName,
  }).outputText;
}

async function loadDomainModule() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "draft-quote-domain-test-"));
  const libDir = path.join(tempDir, "lib");
  try {
    await mkdir(libDir, { recursive: true });
    const source = await readFile(domainSourcePath, "utf8");
    await writeFile(path.join(libDir, "draft-quote-domain.mjs"), transpile(source, domainSourcePath), "utf8");
    return await import(`file://${path.join(libDir, "draft-quote-domain.mjs")}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const { inferProductCodeDomainFromDraftQuote } = await loadDomainModule();

assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "IMPORT", origin_country: "SG", destination_country: "PG" }), "IMPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "EXPORT", origin_country: "PG", destination_country: "AU" }), "EXPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "DOMESTIC", origin_country: "PG", destination_country: "PG" }), "DOMESTIC");
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "SG", destination_country: "PG" }), "IMPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "PG", destination_country: "AU" }), "EXPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "PG", destination_country: "PG" }), "DOMESTIC");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "EXPORT", origin_country: "SG", destination_country: "PG" }), null);
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "", destination_country: "PG" }), null);
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "AU", destination_country: "SG" }), null);

const workflowSource = await readFile(workflowSourcePath, "utf8");
assert.ok(workflowSource.includes("inferProductCodeDomainFromDraftQuote(initialData.shipment_context)"));
assert.ok(workflowSource.includes("domain: productCodeDomain"));
assert.ok(!workflowSource.includes('domain: "IMPORT"'));
assert.ok(!workflowSource.includes("POM") && !workflowSource.includes("LAE") && !workflowSource.includes("HGU"));

console.log("draft quote domain checks passed");
