import type { SpotPricingEnvelope } from "@/lib/spot-types";

type FinalizeEnvelopeState = Pick<
  SpotPricingEnvelope,
  "acknowledgement" | "can_proceed" | "intake_safety" | "is_expired" | "missing_mandatory_fields" | "status"
>;

const NON_BLOCKING_INTAKE_ISSUE_PATTERNS = [
  /low-confidence/i,
  /scanned-pdf fallback/i,
  /fallback extraction/i,
];

function hasOnlyNonBlockingIntakeIssues(issues: string[] | undefined): boolean {
  const cleaned = (issues || []).map((issue) => issue.trim()).filter(Boolean);
  if (cleaned.length === 0) return false;
  return cleaned.every((issue) =>
    NON_BLOCKING_INTAKE_ISSUE_PATTERNS.some((pattern) => pattern.test(issue))
  );
}

export function getSpotFinalizeDisabledReason({
  spe,
  unresolvedReviewIssueCount,
  unresolvedReviewIssueLabels = [],
}: {
  spe: FinalizeEnvelopeState | null | undefined;
  unresolvedReviewIssueCount: number;
  unresolvedReviewIssueLabels?: string[];
}): string | null {
  if (!spe) {
    return "SPOT envelope is still loading.";
  }

  if (spe.is_expired || spe.status === "expired") {
    return "This SPOT envelope has expired. Create a new SPOT quote.";
  }

  if (spe.status === "rejected") {
    return "This SPOT quote is no longer active.";
  }

  if (spe.status !== "draft" && !spe.can_proceed) {
    const missing = spe.missing_mandatory_fields?.length
      ? spe.missing_mandatory_fields.join(", ")
      : "required fields";
    return `Complete missing SPOT fields before creating quote: ${missing}.`;
  }

  if (!spe.acknowledgement && spe.status === "ready") {
    return "SPOT acknowledgement is required before creating quote.";
  }

  if (unresolvedReviewIssueCount > 0) {
    const labels = unresolvedReviewIssueLabels.map((label) => label.trim()).filter(Boolean);
    if (labels.length > 0) {
      const shownLabels = labels.slice(0, 3).join(", ");
      const remainingCount = Math.max(unresolvedReviewIssueCount - 3, 0);
      const suffix = remainingCount > 0 ? `, and ${remainingCount} more` : "";
      return `Resolve ${unresolvedReviewIssueCount} issue${unresolvedReviewIssueCount === 1 ? "" : "s"} before creating quote: ${shownLabels}${suffix}.`;
    }
    return `Resolve ${unresolvedReviewIssueCount} issue${unresolvedReviewIssueCount === 1 ? "" : "s"} before creating quote.`;
  }

  if (
    !spe.acknowledgement &&
    spe.intake_safety &&
    !spe.intake_safety.is_safe_to_quote &&
    !hasOnlyNonBlockingIntakeIssues(spe.intake_safety.blocking_issues)
  ) {
    return spe.intake_safety.blocking_issues?.[0] || "Review imported SPOT source findings before creating quote.";
  }

  return null;
}

export function getSpotFinalizeFormDisabledReason({
  finalizeDisabledReason,
  editableChargeCount,
  isFormValid,
  allowEmptySubmit,
}: {
  finalizeDisabledReason?: string | null;
  editableChargeCount: number;
  isFormValid: boolean;
  allowEmptySubmit: boolean;
}): string | null {
  if (finalizeDisabledReason) {
    return finalizeDisabledReason;
  }

  if (isFormValid) {
    return null;
  }

  if (editableChargeCount === 0 && allowEmptySubmit) {
    return null;
  }

  if (editableChargeCount === 0) {
    return "Add at least one SPOT charge line before creating quote.";
  }

  return "Complete the visible SPOT charge fields before creating quote.";
}
