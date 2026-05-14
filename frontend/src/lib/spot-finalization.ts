import type { SpotPricingEnvelope } from "@/lib/spot-types";

type FinalizeEnvelopeState = Pick<
  SpotPricingEnvelope,
  "acknowledgement" | "can_proceed" | "intake_safety" | "is_expired" | "missing_mandatory_fields" | "status"
>;

export function getSpotFinalizeDisabledReason({
  spe,
  unresolvedReviewIssueCount,
  conditionalAcknowledgementRequired = false,
  conditionalAcknowledgementAccepted = false,
}: {
  spe: FinalizeEnvelopeState | null | undefined;
  unresolvedReviewIssueCount: number;
  conditionalAcknowledgementRequired?: boolean;
  conditionalAcknowledgementAccepted?: boolean;
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
      : "required rate fields";
    return `Complete missing SPOT fields before creating quote: ${missing}.`;
  }

  if (conditionalAcknowledgementRequired && !conditionalAcknowledgementAccepted) {
    return "Acknowledge the conditional SPOT rates before creating quote.";
  }

  if (unresolvedReviewIssueCount > 0) {
    return `Resolve ${unresolvedReviewIssueCount} issue${unresolvedReviewIssueCount === 1 ? "" : "s"} before creating quote.`;
  }

  if (!spe.acknowledgement && spe.intake_safety && !spe.intake_safety.is_safe_to_quote) {
    const blockingIssues = spe.intake_safety.blocking_issues || [];
    const onlyConditionalBlockers =
      conditionalAcknowledgementAccepted &&
      blockingIssues.length > 0 &&
      blockingIssues.every((issue) => issue.toLowerCase().includes("conditional"));
    if (onlyConditionalBlockers) {
      return null;
    }
    return spe.intake_safety.blocking_issues?.[0] || "Review imported SPOT source findings before creating quote.";
  }

  return null;
}
