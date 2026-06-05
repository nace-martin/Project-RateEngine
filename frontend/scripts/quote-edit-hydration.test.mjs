import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const helperSourcePath = path.join(frontendRoot, "src", "lib", "quote-edit-hydration.ts");
const workflowSourcePath = path.join(frontendRoot, "src", "lib", "quote-workflow.ts");

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
  const tempDir = await mkdtemp(path.join(tmpdir(), "quote-edit-hydration-test-"));
  const libDir = path.join(tempDir, "lib");
  const schemaDir = path.join(libDir, "schemas");

  try {
    await mkdir(schemaDir, { recursive: true });

    const helperSource = await readFile(helperSourcePath, "utf8");
    const workflowSource = await readFile(workflowSourcePath, "utf8");

    const helperModule = transpile(helperSource, helperSourcePath)
      .replace(/from ['"]\.\/schemas\/quoteSchema['"]/g, "from './schemas/quoteSchema.mjs'")
      .replace(/from ['"]\.\/quote-workflow['"]/g, "from './quote-workflow.mjs'");

    await writeFile(path.join(libDir, "quote-edit-hydration.mjs"), helperModule, "utf8");
    await writeFile(path.join(libDir, "quote-workflow.mjs"), transpile(workflowSource, workflowSourcePath), "utf8");
    await writeFile(
      path.join(schemaDir, "quoteSchema.mjs"),
      `
export const V3_LOCATION_TYPES = {
  AIRPORT: 'AIRPORT',
  PORT: 'PORT',
  ADDRESS: 'ADDRESS',
  CITY: 'CITY',
};

export const V3_PACKAGE_TYPES = {
  BOX: 'Box',
  PALLET: 'Pallet',
  SKID: 'Skid',
  CRATE: 'Crate',
  CARTON: 'Carton',
  DRUM: 'Drum',
};
`,
      "utf8",
    );

    const helper = await import(`file://${path.join(libDir, "quote-edit-hydration.mjs")}`);
    const workflow = await import(`file://${path.join(libDir, "quote-workflow.mjs")}`);
    return { ...helper, ...workflow };
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

function dimension(overrides = {}) {
  return {
    pieces: 2,
    length_cm: 40,
    width_cm: 30,
    height_cm: 20,
    gross_weight_kg: 25,
    package_type: "Pallet",
    ...overrides,
  };
}

function payload(overrides = {}) {
  return {
    customer_id: "customer-latest",
    contact_id: "contact-latest",
    mode: "AIR",
    incoterm: "EXW",
    payment_term: "COLLECT",
    service_scope: "D2D",
    origin_location_id: "origin-latest",
    destination_location_id: "destination-latest",
    dimensions: [dimension()],
    commodity_code: "DG",
    is_dangerous_goods: true,
    ...overrides,
  };
}

function latestVersion(overrides = {}) {
  return {
    id: "version-1",
    version_number: 1,
    status: "DRAFT",
    created_at: "2026-06-01T00:00:00Z",
    lines: [],
    totals: {
      currency: "PGK",
      total_sell_fcy: "0.00",
      total_sell_fcy_incl_gst: "0.00",
      total_sell_fcy_currency: "PGK",
      has_missing_rates: false,
    },
    payload_json: payload(),
    ...overrides,
  };
}

function quote(overrides = {}) {
  return {
    id: "quote-1",
    quote_number: "DRAFT-1234",
    customer: {
      id: "customer-ref",
      company_name: "Acme Logistics",
    },
    contact: {
      id: "contact-ref",
      name: "Casey Ng",
    },
    mode: "AIR",
    shipment_type: "IMPORT",
    incoterm: "EXW",
    payment_term: "COLLECT",
    service_scope: "D2D",
    output_currency: "PGK",
    origin_location: "BNE - Brisbane Airport",
    destination_location: "POM - Port Moresby",
    status: "DRAFT",
    valid_until: "2026-06-30",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T01:00:00Z",
    request_details_json: payload({
      customer_id: "customer-request",
      contact_id: "contact-request",
      payment_term: "PREPAID",
      service_scope: "A2A",
      origin_location_id: "origin-request",
      destination_location_id: "destination-request",
      commodity_code: "GCR",
      is_dangerous_goods: false,
    }),
    latest_version: latestVersion(),
    quote_result: null,
    ...overrides,
  };
}

const { hydrateQuoteEditForm, buildQuoteComputePayload } = await loadModules();

{
  const hydrated = hydrateQuoteEditForm(quote());

  assert.equal(hydrated.formData.customer_id, "customer-latest");
  assert.equal(hydrated.formData.contact_id, "contact-latest");
  assert.equal(hydrated.formData.payment_term, "COLLECT");
  assert.equal(hydrated.formData.service_scope, "D2D");
  assert.equal(hydrated.formData.origin_location_id, "origin-latest");
  assert.equal(hydrated.formData.destination_location_id, "destination-latest");
  assert.equal(hydrated.formData.cargo_type, "Dangerous Goods");
}

{
  const hydrated = hydrateQuoteEditForm(
    quote({
      latest_version: latestVersion({ payload_json: undefined }),
    }),
  );

  assert.equal(hydrated.formData.customer_id, "customer-request");
  assert.equal(hydrated.formData.contact_id, "contact-request");
  assert.equal(hydrated.formData.payment_term, "PREPAID");
  assert.equal(hydrated.formData.service_scope, "A2A");
  assert.equal(hydrated.formData.origin_location_id, "origin-request");
  assert.equal(hydrated.formData.destination_location_id, "destination-request");
  assert.equal(hydrated.formData.cargo_type, "General Cargo");
}

{
  const hydrated = hydrateQuoteEditForm(
    quote({
      latest_version: latestVersion({
        payload_json: payload({
          dimensions: [
            dimension({
              pieces: 3,
              length_cm: 55,
              width_cm: 44,
              height_cm: 33,
              gross_weight_kg: 66,
              package_type: "Crate",
            }),
          ],
        }),
      }),
    }),
  );

  assert.deepEqual(hydrated.formData.dimensions, [
    {
      pieces: 3,
      length_cm: "55",
      width_cm: "44",
      height_cm: "33",
      gross_weight_kg: "66",
      package_type: "Crate",
    },
  ]);
}

{
  const hydrated = hydrateQuoteEditForm(
    quote({
      latest_version: latestVersion({
        payload_json: {
          customer_id: "customer-nested",
          contact_id: "contact-nested",
          shipment: {
            mode: "AIR",
            incoterm: "DAP",
            payment_term: "PREPAID",
            service_scope: "D2A",
            commodity_code: "PER",
            is_dangerous_goods: false,
            origin_location: { id: "origin-nested" },
            destination_location: { id: "destination-nested" },
            pieces: [
              {
                pieces: 1,
                length_cm: "10",
                width_cm: "20",
                height_cm: "30",
                gross_weight_kg: "40",
                package_type: "Skid",
              },
            ],
          },
        },
      }),
    }),
  );

  assert.equal(hydrated.formData.customer_id, "customer-nested");
  assert.equal(hydrated.formData.contact_id, "contact-nested");
  assert.equal(hydrated.formData.payment_term, "PREPAID");
  assert.equal(hydrated.formData.service_scope, "D2A");
  assert.equal(hydrated.formData.incoterm, "DAP");
  assert.equal(hydrated.formData.origin_location_id, "origin-nested");
  assert.equal(hydrated.formData.destination_location_id, "destination-nested");
  assert.equal(hydrated.formData.cargo_type, "Perishable / Cold Chain");
  assert.deepEqual(hydrated.formData.dimensions, [
    {
      pieces: 1,
      length_cm: "10",
      width_cm: "20",
      height_cm: "30",
      gross_weight_kg: "40",
      package_type: "Skid",
    },
  ]);
}

{
  const hydrated = hydrateQuoteEditForm(quote());

  assert.equal(hydrated.initialCustomer?.id, "customer-ref");
  assert.equal(hydrated.initialCustomer?.name, "Acme Logistics");
  assert.equal(hydrated.initialOrigin?.id, "origin-latest");
  assert.equal(hydrated.initialOrigin?.code, "BNE");
  assert.equal(hydrated.initialDestination?.id, "destination-latest");
  assert.equal(hydrated.initialDestination?.code, "POM");
  assert.equal(hydrated.formData.origin_airport, "BNE");
  assert.equal(hydrated.formData.destination_airport, "POM");
}

{
  const sourceQuote = quote({ id: "quote-submit" });
  const hydrated = hydrateQuoteEditForm(sourceQuote);
  const submitPayload = buildQuoteComputePayload(hydrated.formData, undefined, sourceQuote.id);

  assert.equal(submitPayload.quote_id, "quote-submit");
  assert.equal(submitPayload.customer_id, hydrated.formData.customer_id);
  assert.equal(submitPayload.contact_id, hydrated.formData.contact_id);
}

{
  const hydrated = hydrateQuoteEditForm(
    quote({
      id: "quote-incomplete",
      status: "INCOMPLETE",
      latest_version: latestVersion({
        status: "INCOMPLETE",
        payload_json: payload({
          customer_id: "customer-incomplete",
          service_scope: "D2D",
        }),
      }),
    }),
  );

  assert.equal(hydrated.formData.quote_id, "quote-incomplete");
  assert.equal(hydrated.formData.customer_id, "customer-incomplete");
  assert.equal(hydrated.formData.service_scope, "D2D");
}

console.log("quote edit hydration checks passed");
