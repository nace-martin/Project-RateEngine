import type {
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
} from "@/lib/types";
import type { QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";

type QuoteSpotRateOverrides = {
  carrierSpotRatePgk: string;
  agentDestChargesFcy: string;
  agentCurrency: string;
  isAllIn?: boolean;
};

const DESTINATION_COMPONENT_CODES = [
  "DST-DELIV-STD",
  "DST-CLEAR-CUS",
  "DST-HANDL-STD",
  "DST-DOC-IMP",
  "DST_CHARGES",
];

export const buildQuoteComputePayload = (
  data: QuoteFormSchemaV3,
  spotRates?: QuoteSpotRateOverrides,
  existingQuoteId?: string | null,
): V3QuoteComputeRequest => {
  const payload: V3QuoteComputeRequest = {
    quote_id: existingQuoteId || undefined,
    customer_id: data.customer_id,
    contact_id: data.contact_id,
    mode: data.mode,
    incoterm: data.incoterm,
    payment_term: data.payment_term,
    service_scope: data.service_scope,
    origin_location_id: data.origin_location_id,
    destination_location_id: data.destination_location_id,
    dimensions: data.dimensions.map((dimension) => ({
      pieces: dimension.pieces,
      length_cm: dimension.length_cm,
      width_cm: dimension.width_cm,
      height_cm: dimension.height_cm,
      gross_weight_kg: dimension.gross_weight_kg,
      package_type: dimension.package_type,
    })),
    overrides: data.overrides?.map((override) => ({
      service_component_id: override.service_component_id,
      cost_fcy: override.cost_fcy,
      currency: override.currency,
      unit: override.unit,
      min_charge_fcy: override.min_charge_fcy,
    })),
    is_dangerous_goods: data.cargo_type === "Dangerous Goods",
    output_currency: data.output_currency || undefined,
  };

  if (!spotRates) {
    return payload;
  }

  const spots: Record<string, unknown> = {};

  if (spotRates.carrierSpotRatePgk) {
    spots.FRT_AIR_EXP = {
      amount: spotRates.carrierSpotRatePgk,
      currency: "PGK",
      is_all_in: spotRates.isAllIn,
    };
  }

  if (spotRates.agentDestChargesFcy) {
    spots.DST_CHARGES = {
      amount: spotRates.agentDestChargesFcy,
      currency: spotRates.agentCurrency || "USD",
    };
  }

  if (Object.keys(spots).length > 0) {
    payload.spot_rates = spots;
  }

  return payload;
};

export const getQuoteMissingRateFlags = (response: V3QuoteComputeResponse) => {
  const lines = response.latest_version?.lines ?? [];

  return {
    carrier: lines.some(
      (line) => line.service_component?.code === "FRT_AIR_EXP" && line.is_rate_missing,
    ),
    agent: lines.some(
      (line) =>
        DESTINATION_COMPONENT_CODES.includes(line.service_component?.code || "") &&
        line.is_rate_missing,
    ),
  };
};
