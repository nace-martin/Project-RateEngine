import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

const frontendRoot = path.resolve(process.cwd());

const mapFormPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "MapExistingForm.tsx");
const requestFormPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "RequestProductCodeForm.tsx");
const addFormPath = path.join(frontendRoot, "src", "components", "spot", "workspace", "AddChargeForm.tsx");
const workspacePath = path.join(frontendRoot, "src", "components", "spot", "ExceptionWorkspace.tsx");

console.log("Starting Spot Workspace Form Extraction Assertions...");

// 1. Verify files exist and read content
const mapFormSrc = await readFile(mapFormPath, "utf8");
const requestFormSrc = await readFile(requestFormPath, "utf8");
const addFormSrc = await readFile(addFormPath, "utf8");
const workspaceSrc = await readFile(workspacePath, "utf8");

console.log("✓ Extracted components and parent workspace files loaded successfully.");

// 2. Extracted components must have no API imports or calls
const apiPattern = /import.*from.*(api|lib\/api)/i;
assert.ok(!apiPattern.test(mapFormSrc), "MapExistingForm must not import from API library");
assert.ok(!apiPattern.test(requestFormSrc), "RequestProductCodeForm must not import from API library");
assert.ok(!apiPattern.test(addFormSrc), "AddChargeForm must not import from API library");
assert.ok(!mapFormSrc.includes("fetch("), "MapExistingForm must not perform fetch operations");
assert.ok(!requestFormSrc.includes("fetch("), "RequestProductCodeForm must not perform fetch operations");
assert.ok(!addFormSrc.includes("fetch("), "AddChargeForm must not perform fetch operations");

console.log("✓ Verified zero API imports and fetch operations in extracted forms.");

// 3. ExceptionWorkspace must import the new forms
assert.ok(workspaceSrc.includes('import { MapExistingForm } from "./workspace/MapExistingForm";'), "ExceptionWorkspace must import MapExistingForm");
assert.ok(workspaceSrc.includes('import { RequestProductCodeForm } from "./workspace/RequestProductCodeForm";'), "ExceptionWorkspace must import RequestProductCodeForm");
assert.ok(workspaceSrc.includes('import { AddChargeForm } from "./workspace/AddChargeForm";'), "ExceptionWorkspace must import AddChargeForm");

console.log("✓ Verified ExceptionWorkspace correctly imports the extracted components.");

// 4. MapExistingForm option values and order checks
const options = [];
const selectRegex = /<option value="([^"]*)">/g;
let match;
while ((match = selectRegex.exec(mapFormSrc)) !== null) {
  options.push(match[1]);
}
assert.deepEqual(
  options,
  ["", "AF-FREIGHT", "AF-FUEL", "AF-SEC", "AF-HC"],
  "MapExistingForm select options and order must match exactly"
);

console.log("✓ Verified MapExistingForm contains exact option values and sequence.");

// 5. MapExistingForm checks for non-empty selected values before calling onMap
assert.ok(
  mapFormSrc.includes("if (e.target.value) {") || mapFormSrc.includes("if(e.target.value)"),
  "MapExistingForm must check for non-empty selection before invoking callback"
);

console.log("✓ Verified MapExistingForm enforces non-empty checks before callback.");

// 6. Parent integration: verify callbacks and state ownership
// Verify the parent binds context using currentIssue.id and handles the submissions
assert.ok(
  /handleMapProductCode\s*\(\s*currentIssue\.id\s*,\s*productCode\s*,\s*currentIssue\.title\s*\)/.test(workspaceSrc),
  "ExceptionWorkspace must wrap handleMapProductCode mapping callback with currentIssue context"
);

assert.ok(
  /handleSubmitProductCodeRequest\s*\(\s*currentIssue\.id\s*\)/.test(workspaceSrc),
  "ExceptionWorkspace must wrap handleSubmitProductCodeRequest callback with currentIssue context"
);

assert.ok(
  /handleAddUnknownAsCharge\s*\(\s*currentIssue\.id\s*\)/.test(workspaceSrc),
  "ExceptionWorkspace must wrap handleAddUnknownAsCharge callback with currentIssue context"
);

// Verify parent retains state ownership and handler definitions
assert.ok(workspaceSrc.includes("const handleMapProductCode ="), "ExceptionWorkspace must define and own handleMapProductCode");
assert.ok(workspaceSrc.includes("const handleSubmitProductCodeRequest ="), "ExceptionWorkspace must define and own handleSubmitProductCodeRequest");
assert.ok(workspaceSrc.includes("const handleAddUnknownAsCharge ="), "ExceptionWorkspace must define and own handleAddUnknownAsCharge");

console.log("✓ Verified parent-bound callbacks wrap handlers and preserve local state ownership.");

// 7. Verify wizard variables and decision constructs remain in ExceptionWorkspace
assert.ok(workspaceSrc.includes("unknownStep"), "ExceptionWorkspace must own and manage unknownStep state");
assert.ok(workspaceSrc.includes("unknownClassification"), "ExceptionWorkspace must own and manage unknownClassification state");
assert.ok(workspaceSrc.includes("interface Decision"), "ExceptionWorkspace must own Decision interfaces");
assert.ok(workspaceSrc.includes("const [decisions"), "ExceptionWorkspace must own the decisions array state");

console.log("✓ Verified unknown-charge wizard flow and decision logging reside strictly in parent.");

console.log("All Phase 14C form-extraction contract assertions passed successfully!");
