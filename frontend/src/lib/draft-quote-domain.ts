import type { DraftQuote } from "./draft-quote-types";

const PRODUCT_CODE_DOMAINS = new Set(["IMPORT", "EXPORT", "DOMESTIC"]);
const PNG_COUNTRY_VALUES = new Set(["PG", "PNG", "PAPUA NEW GUINEA"]);

export type DraftQuoteDomainIssueCode = "MISSING_ROUTE_EVIDENCE" | "UNSUPPORTED_ROUTE";

export interface DraftQuoteDomainResolution {
    domain: string | null;
    issueCode: DraftQuoteDomainIssueCode | null;
    issueMessage: string | null;
}

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

export function resolveProductCodeDomainFromDraftQuote(shipmentContext: DraftQuote["shipment_context"]): DraftQuoteDomainResolution {
    const serverDirection = normalizeDomain(shipmentContext.direction);
    if (serverDirection) {
        return { domain: serverDirection, issueCode: null, issueMessage: null };
    }

    const originCountry = String(shipmentContext.origin_country || "").trim();
    const destinationCountry = String(shipmentContext.destination_country || "").trim();
    const routeDomain = inferDomainFromTrustedCountries(shipmentContext);
    if (routeDomain) {
        return { domain: routeDomain, issueCode: null, issueMessage: null };
    }

    if (!originCountry || !destinationCountry) {
        return {
            domain: null,
            issueCode: "MISSING_ROUTE_EVIDENCE",
            issueMessage: "Draft Quote is missing server direction and trusted route countries; ProductCode request cannot be submitted.",
        };
    }

    return {
        domain: null,
        issueCode: "UNSUPPORTED_ROUTE",
        issueMessage: "Draft Quote route is outside supported PNG import/export/domestic scope; ProductCode request cannot be submitted.",
    };
}

export function inferProductCodeDomainFromDraftQuote(shipmentContext: DraftQuote["shipment_context"]): string | null {
    return resolveProductCodeDomainFromDraftQuote(shipmentContext).domain;
}
