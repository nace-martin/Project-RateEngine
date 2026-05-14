export type SpotChargeReadinessLine = {
  bucket?: string | null;
  is_primary_cost?: boolean | null;
};

export function getSpotChargeFormDisabledReason({
  charges,
  isFormValid,
}: {
  charges: SpotChargeReadinessLine[];
  isFormValid: boolean;
}): string | null {
  if (charges.length === 0) {
    return "Add at least one matched or manually entered SPOT charge before creating quote.";
  }

  const airfreightCharges = charges.filter((charge) => charge.bucket === "airfreight");
  if (airfreightCharges.length > 0) {
    const primaryCount = airfreightCharges.filter((charge) => Boolean(charge.is_primary_cost)).length;
    if (primaryCount !== 1) {
      return "Select exactly one primary airfreight line before creating quote.";
    }
  }

  if (!isFormValid) {
    return "Resolve invalid SPOT charge line fields before creating quote.";
  }

  return null;
}
