import type { DraftQuote } from "./draft-quote-types";

const PRODUCT_CODE_DOMAINS = new Set(["IMPORT", "EXPORT", "DOMESTIC"]);
const PNG_COUNTRY_VALUES = new Set(["PG", "PNG", "PAPUA NEW GUINEA"]);

function normalizeDomain(value: unknown): string | null {
    const normalized = String(value || "").trim().toUpperCase();
    return PRODUCT_CODE_DOMAINS.has(normalized) ? normalized : null;
}

function isPngCountry(value: unknown): boolean {
    return PNG_COUNTRY_VALUES.has(String(value || "").trim().toUpperCase());
}

function inferDomainFromTrustedCountries(shipmentContext: DraftQuote["shipment_context"]): string | null {
    const originCountry = String(shipmentContext.origin_country || "").trim();
    const destinationCountry = String(shipmentContext.destination_country || "").trim();
    if (!originCountry || !destinationCountry) return null;

    const originIsPng = isPngCountry(originCountry);
    const destinationIsPng = isPngCountry(destinationCountry);
    if (originIsPng && destinationIsPng) return "DOMESTIC";
    if (originIsPng && !destinationIsPng) return "EXPORT";
    if (!originIsPng && destinationIsPng) return "IMPORT";
    return null;
}

export function inferProductCodeDomainFromDraftQuote(shipmentContext: DraftQuote["shipment_context"]): string | null {
    const serverDirection = normalizeDomain(shipmentContext.direction);
    const routeDomain = inferDomainFromTrustedCountries(shipmentContext);

    if (serverDirection && routeDomain && serverDirection !== routeDomain) {
        return null;
    }

    return serverDirection || routeDomain;
}
