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

const { inferProductCodeDomainFromDraftQuote, resolveProductCodeDomainFromDraftQuote } = await loadDomainModule();

// Server-derived Draft Quote direction is authoritative for frontend filtering/request metadata.
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "IMPORT", origin_country: "CN", destination_country: "PG", origin_code: "CAN", destination_code: "POM" }), "IMPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "EXPORT", origin_country: "PG", destination_country: "AU" }), "EXPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "DOMESTIC", origin_country: "PG", destination_country: "PG" }), "DOMESTIC");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "IMPORT", origin_country: "PG", destination_country: "AU" }), "IMPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "EXPORT", origin_country: "SG", destination_country: "PG" }), "EXPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ direction: "DOMESTIC", origin_country: "AU", destination_country: "SG" }), "DOMESTIC");

// Country inference is fallback only when the server direction is absent.
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "SG", destination_country: "PG" }), "IMPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "PG", destination_country: "AU" }), "EXPORT");
assert.equal(inferProductCodeDomainFromDraftQuote({ origin_country: "PG", destination_country: "PG" }), "DOMESTIC");

// Missing and unsupported trusted route evidence fail closed with distinct visible diagnostics.
assert.deepEqual(resolveProductCodeDomainFromDraftQuote({ origin_country: "", destination_country: "PG" }), {
  domain: null,
  issueCode: "MISSING_ROUTE_EVIDENCE",
  issueMessage: "Draft Quote is missing server direction and trusted route countries; ProductCode request cannot be submitted.",
});
assert.deepEqual(resolveProductCodeDomainFromDraftQuote({ origin_country: "AU", destination_country: "SG" }), {
  domain: null,
  issueCode: "UNSUPPORTED_ROUTE",
  issueMessage: "Draft Quote route is outside supported PNG import/export/domestic scope; ProductCode request cannot be submitted.",
});

const workflowSource = await readFile(workflowSourcePath, "utf8");
assert.ok(workflowSource.includes("resolveProductCodeDomainFromDraftQuote(initialData.shipment_context)"));
assert.ok(workflowSource.includes("domain: productCodeDomain"));
assert.ok(workflowSource.includes("Backend rejected ProductCode request"));
assert.ok(!workflowSource.includes('domain: "IMPORT"'));
assert.ok(!workflowSource.includes("POM") && !workflowSource.includes("LAE") && !workflowSource.includes("HGU"));

console.log("draft quote domain checks passed");
