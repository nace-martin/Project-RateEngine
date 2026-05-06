import type {
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
} from "@/lib/types";
import type { QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";

export type SPEOverrides = {
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

export const CARGO_TYPE_TO_COMMODITY_CODE: Record<string, string> = {
  "General Cargo": "GCR",
  "Dangerous Goods": "DG",
  "Perishable / Cold Chain": "PER",
  "Live Animals": "AVI",
  "Valuable / High-Value": "HVC",
  "Oversized / OOG": "OOG",
};

export const getCargoTypeForCommodityCode = (
  commodityCode?: string | null,
  isDangerousGoods?: boolean,
): QuoteFormSchemaV3["cargo_type"] => {
  switch ((commodityCode || "").trim().toUpperCase()) {
    case "DG":
      return "Dangerous Goods";
    case "PER":
      return "Perishable / Cold Chain";
    case "AVI":
      return "Live Animals";
    case "HVC":
      return "Valuable / High-Value";
    case "OOG":
      return "Oversized / OOG";
    default:
      return isDangerousGoods ? "Dangerous Goods" : "General Cargo";
  }
};

export const buildQuoteComputePayload = (
  data: QuoteFormSchemaV3,
  speOverrides?: SPEOverrides,
  existingQuoteId?: string | null,
): V3QuoteComputeRequest => {
  const commodityCode = CARGO_TYPE_TO_COMMODITY_CODE[data.cargo_type] || "GCR";
  const payload: V3QuoteComputeRequest = {
    quote_id: existingQuoteId || undefined,
    opportunity_id: data.opportunity_id,
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
    commodity_code: commodityCode,
    overrides: data.overrides?.map((override) => ({
      service_component_id: override.service_component_id,
      cost_fcy: override.cost_fcy,
      currency: override.currency,
      unit: override.unit,
      min_charge_fcy: override.min_charge_fcy,
    })),
    is_dangerous_goods: commodityCode === "DG",
    output_currency: data.output_currency || undefined,
  };

  const counterpartyMatch = data.pricing_counterparty?.match(/^(agent|carrier):(\d+)$/);
  if (counterpartyMatch) {
    const [, kind, id] = counterpartyMatch;
    if (kind === "agent") {
      payload.agent_id = Number(id);
    } else {
      payload.carrier_id = Number(id);
    }
  }

  if (!speOverrides) {
    return payload;
  }

  const spots: Record<string, unknown> = {};

  if (speOverrides.carrierSpotRatePgk) {
    spots.FRT_AIR_EXP = {
      amount: speOverrides.carrierSpotRatePgk,
      currency: "PGK",
      is_all_in: speOverrides.isAllIn,
    };
  }

  if (speOverrides.agentDestChargesFcy) {
    spots.DST_CHARGES = {
      amount: speOverrides.agentDestChargesFcy,
      currency: speOverrides.agentCurrency || "USD",
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
