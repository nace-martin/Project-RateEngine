import type { LocationSearchResult } from "@/lib/types";

export const SERVICE_SCOPE_LABELS: Record<string, string> = {
  D2D: "Door to Door",
  A2D: "Airport to Door",
  D2A: "Door to Airport",
  A2A: "Airport to Airport",
  P2P: "Airport to Airport",
};

export const SERVICE_SCOPE_OPTIONS = [
  { value: "D2D", label: SERVICE_SCOPE_LABELS.D2D },
  { value: "D2A", label: SERVICE_SCOPE_LABELS.D2A },
  { value: "A2D", label: SERVICE_SCOPE_LABELS.A2D },
  { value: "A2A", label: SERVICE_SCOPE_LABELS.A2A },
] as const;

export const PAYMENT_TERM_LABELS: Record<string, string> = {
  PREPAID: "Prepaid",
  COLLECT: "Collect",
  THIRD_PARTY: "Third Party",
};

export const INCOTERM_LABELS: Record<string, string> = {
  EXW: "Ex Works",
  FCA: "Free Carrier",
  FOB: "Free On Board",
  CPT: "Carriage Paid To",
  DAP: "Delivered at Place",
  DDP: "Delivered Duty Paid",
  CFR: "Cost and Freight",
};

const LOCATION_CODE_PATTERN = /\(([A-Z]{3})\)/;
const INLINE_SEPARATOR = " \u2022 ";
const ROUTE_SEPARATOR = " \u2192 ";

export const formatServiceScope = (scope?: string | null, fallback = "N/A") => {
  const normalized = (scope || "").toUpperCase().trim();
  return SERVICE_SCOPE_LABELS[normalized] || normalized || fallback;
};

export const formatPaymentTerm = (term?: string | null, fallback = "N/A") => {
  const normalized = (term || "").toUpperCase().trim();
  return PAYMENT_TERM_LABELS[normalized] || normalized || fallback;
};

export const formatIncoterm = (
  incoterm?: string | null,
  options?: { includeDescription?: boolean; fallback?: string },
) => {
  const normalized = (incoterm || "").toUpperCase().trim();
  if (!normalized) {
    return options?.fallback || "N/A";
  }

  if (options?.includeDescription === false) {
    return normalized;
  }

  const description = INCOTERM_LABELS[normalized];
  return description ? `${normalized} (${description})` : normalized;
};

export const formatPieceLabel = (pieces: number) =>
  `${pieces} ${pieces === 1 ? "piece" : "pieces"}`;

export const joinDisplayValues = (values: Array<string | null | undefined>) =>
  values
    .map((value) => value?.trim())
    .filter((value): value is string => Boolean(value))
    .join(INLINE_SEPARATOR);

export const formatLocationName = (
  location: Pick<LocationSearchResult, "display_name"> | null | undefined,
  fallbackCode = "",
) => {
  const rawLabel = location?.display_name?.trim() || "";
  if (!rawLabel) {
    return fallbackCode;
  }

  const withoutCodeSuffix = rawLabel.replace(LOCATION_CODE_PATTERN, "").trim();
  const withoutCountrySuffix = withoutCodeSuffix.split(",")[0]?.trim() || withoutCodeSuffix;

  if (withoutCountrySuffix.includes(" - ")) {
    const [, trailingName] = withoutCountrySuffix.split(" - ");
    return trailingName?.trim() || withoutCountrySuffix;
  }

  return withoutCountrySuffix;
};

export const formatRouteName = (
  origin: Pick<LocationSearchResult, "display_name"> | null | undefined,
  destination: Pick<LocationSearchResult, "display_name"> | null | undefined,
  originCode = "",
  destinationCode = "",
) => {
  const originName = formatLocationName(origin, originCode);
  const destinationName = formatLocationName(destination, destinationCode);
  if (!originName || !destinationName) {
    return "";
  }
  return `${originName}${ROUTE_SEPARATOR}${destinationName}`;
};

export const formatRouteCodes = (originCode?: string | null, destinationCode?: string | null) => {
  const normalizedOrigin = (originCode || "").trim().toUpperCase();
  const normalizedDestination = (destinationCode || "").trim().toUpperCase();
  if (!normalizedOrigin || !normalizedDestination) {
    return "";
  }
  return `${normalizedOrigin}${ROUTE_SEPARATOR}${normalizedDestination}`;
};
