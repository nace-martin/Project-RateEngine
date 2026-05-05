import type { QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";

export type QuotePrefillParams = {
  companyId?: string | null;
  opportunityId?: string | null;
  serviceType?: string | null;
  originLocationId?: string;
  destinationLocationId?: string;
  originCode?: string;
  destinationCode?: string;
};

export type QuotePrefillResult = {
  defaultValues: Partial<QuoteFormSchemaV3>;
  unsupportedServiceType?: string;
};

const SUPPORTED_SERVICE_TYPE_MODES: Record<string, QuoteFormSchemaV3["mode"]> = {
  AIR: "AIR",
};

const normalizedServiceType = (serviceType?: string | null) => (serviceType || "").trim().toUpperCase();

export const quoteModeFromServiceType = (
  serviceType?: string | null,
): QuoteFormSchemaV3["mode"] | undefined => SUPPORTED_SERVICE_TYPE_MODES[normalizedServiceType(serviceType)];

export const buildQuotePrefillDefaults = ({
  companyId,
  opportunityId,
  serviceType,
  originLocationId,
  destinationLocationId,
  originCode,
  destinationCode,
}: QuotePrefillParams): QuotePrefillResult => {
  const mode = quoteModeFromServiceType(serviceType);
  const serviceTypeKey = normalizedServiceType(serviceType);
  const shouldLinkOpportunity = Boolean(opportunityId) && (!serviceTypeKey || Boolean(mode));
  const defaultValues: Partial<QuoteFormSchemaV3> = {
    customer_id: companyId || "",
    opportunity_id: shouldLinkOpportunity ? opportunityId || undefined : undefined,
    origin_location_id: originLocationId || "",
    destination_location_id: destinationLocationId || "",
    origin_airport: originCode || "",
    destination_airport: destinationCode || "",
  };

  if (mode) {
    defaultValues.mode = mode;
  }

  return {
    defaultValues,
    unsupportedServiceType: serviceTypeKey && !mode ? serviceTypeKey : undefined,
  };
};
