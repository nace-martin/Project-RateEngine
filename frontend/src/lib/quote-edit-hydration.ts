import { V3_LOCATION_TYPES, V3_PACKAGE_TYPES, type QuoteFormSchemaV3 } from './schemas/quoteSchema';
import {
  type CompanySearchResult,
  type LocationSearchResult,
  type QuoteContactRef,
  type QuoteCustomerRef,
  type V3DimensionInput,
  type V3QuoteComputeResponse,
} from './types';
import { getCargoTypeForCommodityCode } from './quote-workflow';

export type QuoteEditHydrationResult = {
  formData: Partial<QuoteFormSchemaV3>;
  customerId: string;
  initialCustomer?: CompanySearchResult;
  initialOrigin?: LocationSearchResult;
  initialDestination?: LocationSearchResult;
};

export function hydrateQuoteEditForm(quote: V3QuoteComputeResponse): QuoteEditHydrationResult {
  const payload =
    (quote.latest_version?.payload_json as Record<string, unknown> | undefined)
    ?? (quote.request_details_json as Record<string, unknown> | undefined);
  if (!payload) throw new Error("No payload found on quote");

  const shipmentPayload = (
    payload.shipment && typeof payload.shipment === "object"
      ? (payload.shipment as Record<string, unknown>)
      : undefined
  );

  let dimensions: QuoteFormSchemaV3["dimensions"] = [{
    pieces: 1,
    length_cm: "",
    width_cm: "",
    height_cm: "",
    gross_weight_kg: "",
    package_type: "Box",
  }];

  const rawDimensions = Array.isArray(payload.dimensions)
    ? (payload.dimensions as V3DimensionInput[])
    : Array.isArray(shipmentPayload?.pieces)
      ? (shipmentPayload.pieces as V3DimensionInput[])
      : [];

  if (rawDimensions.length > 0) {
    dimensions = rawDimensions.map((d: V3DimensionInput) => ({
      pieces: d.pieces,
      length_cm: String(d.length_cm),
      width_cm: String(d.width_cm),
      height_cm: String(d.height_cm),
      gross_weight_kg: String(d.gross_weight_kg),
      package_type: Object.values(V3_PACKAGE_TYPES).includes(d.package_type as typeof V3_PACKAGE_TYPES[keyof typeof V3_PACKAGE_TYPES])
        ? (d.package_type as typeof V3_PACKAGE_TYPES[keyof typeof V3_PACKAGE_TYPES])
        : V3_PACKAGE_TYPES.BOX,
    }));
  }

  const originAirportCode = extractAirportCode(quote.origin_location as string);
  const destinationAirportCode = extractAirportCode(quote.destination_location as string);

  const customerId = String(payload.customer_id || "");
  const contactId = String(
    payload.contact_id
    || (quote.contact as QuoteContactRef)?.id
    || ""
  );
  const originLocationId = String(
    payload.origin_location_id
    || ((shipmentPayload?.origin_location as Record<string, unknown> | undefined)?.id ?? "")
  );
  const destinationLocationId = String(
    payload.destination_location_id
    || ((shipmentPayload?.destination_location as Record<string, unknown> | undefined)?.id ?? "")
  );
  const mode = String(payload.mode || shipmentPayload?.mode || "AIR");
  const incoterm = String(payload.incoterm || shipmentPayload?.incoterm || "EXW");
  const paymentTerm = String(payload.payment_term || shipmentPayload?.payment_term || "PREPAID");
  const serviceScope = String(payload.service_scope || shipmentPayload?.service_scope || "A2A");
  const commodityCode = String(
    payload.commodity_code
    || shipmentPayload?.commodity_code
    || ""
  );
  const isDangerousGoods = Boolean(
    payload.is_dangerous_goods
    ?? shipmentPayload?.is_dangerous_goods
  );

  const formData: Partial<QuoteFormSchemaV3> = {
    quote_id: quote.id,
    customer_id: customerId,
    contact_id: contactId,
    mode: (mode as QuoteFormSchemaV3['mode']) || "AIR",
    incoterm: (incoterm as QuoteFormSchemaV3['incoterm']) || "EXW",
    payment_term: (paymentTerm as QuoteFormSchemaV3['payment_term']) || "PREPAID",
    service_scope: (serviceScope as QuoteFormSchemaV3['service_scope']) || "A2A",
    origin_airport: originAirportCode,
    destination_airport: destinationAirportCode,
    origin_location_id: originLocationId,
    destination_location_id: destinationLocationId,
    origin_location_type: V3_LOCATION_TYPES.AIRPORT,
    destination_location_type: V3_LOCATION_TYPES.AIRPORT,
    cargo_type: getCargoTypeForCommodityCode(commodityCode, isDangerousGoods),
    dimensions: dimensions,
  };

  const custRef = quote.customer as QuoteCustomerRef;
  const initialCustomer = customerId && custRef && typeof custRef === 'object'
    ? ({
      id: custRef.id || customerId,
      name: custRef.company_name || custRef.name || "Customer",
    } as CompanySearchResult)
    : undefined;

  const initialOrigin = originLocationId
    ? ({
      id: originLocationId,
      display_name: quote.origin_location as string || originLocationId,
      code: originAirportCode || "ORG",
      type: 'AIRPORT',
      country_code: 'PG',
    } as LocationSearchResult)
    : undefined;

  const initialDestination = destinationLocationId
    ? ({
      id: destinationLocationId,
      display_name: quote.destination_location as string || destinationLocationId,
      code: destinationAirportCode || "DST",
      type: 'AIRPORT',
      country_code: 'AU',
    } as LocationSearchResult)
    : undefined;

  return {
    formData,
    customerId,
    initialCustomer,
    initialOrigin,
    initialDestination,
  };
}

function extractAirportCode(locationStr: string | undefined | null): string {
  if (!locationStr) return "";
  const match = locationStr.match(/^([A-Z]{3})\s*-/);
  if (match) return match[1];
  if (/^[A-Z]{3}$/.test(locationStr.trim())) return locationStr.trim();
  return "";
}
