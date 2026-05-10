import type { LocationSearchResult } from "@/lib/types";

const DOOR_PORTS = new Set(["POM", "LAE"]);
const PNG_AIRPORT_CODES = new Set([
  "POM",
  "LAE",
  "HGU",
  "GKA",
  "RAB",
  "WWK",
  "KVG",
  "MAG",
  "GUR",
  "TBG",
  "HKN",
  "KIE",
]);

const AIRPORT_COUNTRY_MAP: Record<string, string> = {
  ...Object.fromEntries(Array.from(PNG_AIRPORT_CODES).map((code) => [code, "PG"])),
  SIN: "SG",
  HKG: "HK",
  BNE: "AU",
  SYD: "AU",
  CNS: "AU",
  NAN: "FJ",
  HIR: "SB",
  VLI: "VU",
};

export const DOMESTIC_DOOR_PORT_LABEL = "POM or LAE";

export const resolveCountryCode = (
  location: LocationSearchResult | null,
  airportCode?: string,
): string => {
  const explicit = (location?.country_code || "").trim().toUpperCase();
  if (explicit) return explicit;

  const displayName = location?.display_name || "";
  const displayMatch = displayName.match(/,\s*([A-Z]{2})\s*$/i);
  if (displayMatch?.[1]) {
    return displayMatch[1].toUpperCase();
  }

  const code = (airportCode || location?.code || "").trim().toUpperCase();
  return AIRPORT_COUNTRY_MAP[code] || "OTHER";
};

export const isDomesticPngRoute = (
  originCountry: string,
  destinationCountry: string,
  originCode?: string,
  destinationCode?: string,
) => {
  const normalizedOriginCountry = (originCountry || "").trim().toUpperCase();
  const normalizedDestinationCountry = (destinationCountry || "").trim().toUpperCase();
  const origin = (originCode || "").trim().toUpperCase();
  const destination = (destinationCode || "").trim().toUpperCase();

  return (
    normalizedOriginCountry === "PG" &&
    normalizedDestinationCountry === "PG" &&
    Boolean(origin) &&
    Boolean(destination)
  );
};

export const getDomesticServiceScopeError = (
  serviceScope: string | undefined,
  originCode: string | undefined,
  destinationCode: string | undefined,
  originCountry: string,
  destinationCountry: string,
) => {
  const scope = (serviceScope || "").trim().toUpperCase();
  const origin = (originCode || "").trim().toUpperCase();
  const destination = (destinationCode || "").trim().toUpperCase();

  if (!isDomesticPngRoute(originCountry, destinationCountry, origin, destination)) {
    return "";
  }

  if ((scope === "D2D" || scope === "D2A") && !DOOR_PORTS.has(origin)) {
    return `Pickup is only available from ${DOMESTIC_DOOR_PORT_LABEL} for domestic routes.`;
  }

  if ((scope === "D2D" || scope === "A2D") && !DOOR_PORTS.has(destination)) {
    return `Delivery is only available to ${DOMESTIC_DOOR_PORT_LABEL} for domestic routes.`;
  }

  return "";
};

export const isDomesticServiceScopeAvailable = (
  serviceScope: string,
  originCode: string | undefined,
  destinationCode: string | undefined,
  originCountry: string,
  destinationCountry: string,
) =>
  !getDomesticServiceScopeError(
    serviceScope,
    originCode,
    destinationCode,
    originCountry,
    destinationCountry,
  );
