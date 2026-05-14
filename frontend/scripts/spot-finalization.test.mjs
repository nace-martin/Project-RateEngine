import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import ts from "typescript";

const frontendRoot = path.resolve(process.cwd());
const sourcePath = path.join(frontendRoot, "src", "lib", "spot-finalization.ts");

async function loadModule() {
  const source = await readFile(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2020,
    },
    fileName: sourcePath,
  }).outputText;

  const tempDir = await mkdtemp(path.join(tmpdir(), "spot-finalization-test-"));
  const modulePath = path.join(tempDir, "spot-finalization.mjs");

  try {
    await writeFile(modulePath, transpiled, "utf8");
    return await import(`file://${modulePath}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

const {
  getSpotFinalizeDisabledReason,
  getSpotFinalizeFormDisabledReason,
} = await loadModule();

const baseSpe = {
  acknowledgement: null,
  can_proceed: true,
  intake_safety: {
    is_safe_to_quote: true,
    blocking_issues: [],
    pending_source_batch_ids: [],
    pending_source_labels: [],
    review_note_required_batch_ids: [],
  },
  is_expired: false,
  missing_mandatory_fields: [],
  status: "draft",
};

assert.equal(
  getSpotFinalizeDisabledReason({
    spe: {
      ...baseSpe,
      status: "ready",
      acknowledgement: {
        acknowledged_by_user_id: "1",
        acknowledged_at: "2026-05-09T00:00:00Z",
        statement: "I acknowledge this is a conditional SPOT quote and not guaranteed",
      },
    },
    unresolvedReviewIssueCount: 0,
  }),
  null,
  "acknowledged SPOT envelope should be allowed to create quote",
);

assert.match(
  getSpotFinalizeDisabledReason({
    spe: baseSpe,
    unresolvedReviewIssueCount: 2,
    unresolvedReviewIssueLabels: ["Import Air Freight", "Documentation Fee"],
  }) || "",
  /Resolve 2 issues before creating quote: Import Air Freight, Documentation Fee\./,
  "unresolved charge blockers should name affected charges",
);

assert.equal(
  getSpotFinalizeDisabledReason({
    spe: {
      ...baseSpe,
      can_proceed: false,
      missing_mandatory_fields: ["rate"],
    },
    unresolvedReviewIssueCount: 0,
  }),
  null,
  "draft SPOT envelopes should still allow submit so entered charges can be saved before acknowledgement",
);

assert.match(
  getSpotFinalizeDisabledReason({
    spe: {
      ...baseSpe,
      status: "ready",
      can_proceed: false,
      missing_mandatory_fields: ["currency"],
    },
    unresolvedReviewIssueCount: 0,
  }) || "",
  /acknowledgement is required/,
  "ready envelopes without acknowledgement should expose the invalid acknowledgement state first",
);

assert.equal(
  getSpotFinalizeDisabledReason({
    spe: {
      ...baseSpe,
      status: "ready",
      acknowledgement: {
        acknowledged_by_user_id: "1",
        acknowledged_at: "2026-05-09T00:00:00Z",
        statement: "I acknowledge this is a conditional SPOT quote and not guaranteed",
      },
      intake_safety: {
        is_safe_to_quote: false,
        blocking_issues: ["Uploaded PDF: Scanned-PDF fallback extraction was used; verify the imported lines carefully."],
        pending_source_batch_ids: ["source-1"],
        pending_source_labels: ["Uploaded PDF"],
        review_note_required_batch_ids: [],
      },
    },
    unresolvedReviewIssueCount: 0,
  }),
  null,
  "unsafe extraction fallback should not silently disable create when acknowledgement already permits backend proceed",
);

assert.match(
  getSpotFinalizeDisabledReason({
    spe: {
      ...baseSpe,
      intake_safety: {
        is_safe_to_quote: false,
        blocking_issues: ["Agent reply: Possible missed charges: destination handling"],
        pending_source_batch_ids: ["source-1"],
        pending_source_labels: ["Agent reply"],
        review_note_required_batch_ids: ["source-1"],
      },
    },
    unresolvedReviewIssueCount: 0,
  }) || "",
  /Possible missed charges/,
  "unacknowledged source blockers should show the backend blocking issue",
);

assert.equal(
  getSpotFinalizeDisabledReason({
    spe: {
      ...baseSpe,
      intake_safety: {
        is_safe_to_quote: false,
        blocking_issues: ["Uploaded rates: 2 extracted charge line(s) were low-confidence."],
        pending_source_batch_ids: ["source-1"],
        pending_source_labels: ["Uploaded rates"],
        review_note_required_batch_ids: [],
      },
    },
    unresolvedReviewIssueCount: 0,
  }),
  null,
  "low-confidence source warnings should stay visible but not disable final quote creation",
);

const readyAcknowledgedSpe = {
  acknowledgement: { acknowledged_at: "2026-05-11T00:00:00Z" },
  can_proceed: true,
  intake_safety: { is_safe_to_quote: false, blocking_issues: ["AI audit flagged fallback extraction."] },
  is_expired: false,
  missing_mandatory_fields: [],
  status: "ready",
};

assert.equal(
  getSpotFinalizeDisabledReason({
    spe: readyAcknowledgedSpe,
    unresolvedReviewIssueCount: 0,
  }),
  null,
  "acknowledged unsafe-audit fallback must not block when backend can proceed",
);

assert.equal(
  getSpotFinalizeFormDisabledReason({
    finalizeDisabledReason: null,
    editableChargeCount: 0,
    isFormValid: false,
    allowEmptySubmit: true,
  }),
  null,
  "ready SPEs with no editable manual rows must still be submittable",
);

assert.match(
  getSpotFinalizeFormDisabledReason({
    finalizeDisabledReason: null,
    editableChargeCount: 0,
    isFormValid: false,
    allowEmptySubmit: false,
  }),
  /at least one SPOT charge line/,
);

assert.match(
  getSpotFinalizeFormDisabledReason({
    finalizeDisabledReason: null,
    editableChargeCount: 2,
    isFormValid: false,
    allowEmptySubmit: true,
  }),
  /Complete the visible SPOT charge fields/,
);

assert.equal(
  getSpotFinalizeFormDisabledReason({
    finalizeDisabledReason: "Resolve 1 issue before creating quote.",
    editableChargeCount: 0,
    isFormValid: false,
    allowEmptySubmit: true,
  }),
  "Resolve 1 issue before creating quote.",
);

console.log("spot finalization checks passed");
