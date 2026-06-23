import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const sharedSourcePath = path.join(frontendRoot, "src", "lib", "api", "shared.ts");

function transpile(source, fileName) {
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName,
  }).outputText;
}

async function loadSharedApi() {
  const tempDir = await mkdtemp(path.join(tmpdir(), "rbac-error-response-test-"));
  const apiDir = path.join(tempDir, "lib", "api");
  const libDir = path.join(tempDir, "lib");

  try {
    await mkdir(apiDir, { recursive: true });
    await mkdir(libDir, { recursive: true });

    const sharedSource = await readFile(sharedSourcePath, "utf8");
    const sharedModule = transpile(sharedSource, sharedSourcePath).replace(
      /from ['"]\.\.\/config['"]/g,
      "from '../config.mjs'",
    );

    await writeFile(path.join(apiDir, "shared.mjs"), sharedModule, "utf8");
    await writeFile(path.join(libDir, "config.mjs"), `export const API_BASE_URL = "http://testserver";`, "utf8");

    return await import(`file://${path.join(apiDir, "shared.mjs")}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const { parseErrorResponse } = await loadSharedApi();

{
  const response = new Response(JSON.stringify({ error: "Selected contact is not available for this customer/user." }), {
    status: 400,
    headers: { "content-type": "application/json" },
  });
  assert.equal(await parseErrorResponse(response), "Selected contact is not available for this customer/user.");
}

{
  const response = new Response(JSON.stringify({ message: "Customer is outside your active scope." }), {
    status: 403,
    headers: { "content-type": "application/json" },
  });
  assert.equal(await parseErrorResponse(response), "Customer is outside your active scope.");
}

{
  const response = new Response("not json", { status: 404, statusText: "Not Found" });
  assert.equal(await parseErrorResponse(response), "This record is not available to your current scope.");
}

console.log("RBAC error response tests passed");
