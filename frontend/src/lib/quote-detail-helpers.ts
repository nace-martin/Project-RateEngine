import { V3QuoteComputeResponse, QuoteComputeResult } from './types';
import type { SPECommodity } from './spot-types';
import { getCustomerName } from './quote-helpers';

export type SpotResumeContext = {
  originCode: string;
  destinationCode: string;
  originCountry: string;
  destinationCountry: string;
  commodity: SPECommodity;
  serviceScope: string;
  paymentTerm: "PREPAID" | "COLLECT";
  chargeableWeight: number;
  pieces: number;
  outputCurrency: string;
  shipmentType: string;
  customerId: string | null;
  customerName: string;
};

export const SPOT_AIRPORT_COUNTRY_MAP: Record<string, string> = {
  POM: "PG",
  LAE: "PG",
  MTV: "PG",
  SIN: "SG",
  HKG: "HK",
  BNE: "AU",
  SYD: "AU",
  CNS: "AU",
  NAN: "FJ",
  HIR: "SB",
  VLI: "VU",
};

export function normalizeAirportCode(...candidates: unknown[]): string {
  for (const candidate of candidates) {
    const value = String(candidate || "").trim().toUpperCase();
    if (!value) continue;
    if (/^[A-Z]{3}$/.test(value)) return value;
    const match = value.match(/^([A-Z]{3})\s*-/);
    if (match?.[1]) return match[1];
  }
  return "";
}

export function normalizeCountryCode(...candidates: unknown[]): string {
  for (let index = 0; index < candidates.length - 1; index += 1) {
    const value = String(candidates[index] || "").trim().toUpperCase();
    if (/^[A-Z]{2}$/.test(value)) return value;
  }
  const airportCode = String(candidates[candidates.length - 1] || "").trim().toUpperCase();
  return SPOT_AIRPORT_COUNTRY_MAP[airportCode] || "OTHER";
}

export function computeShipmentMetrics(quote: V3QuoteComputeResponse) {
  const payload = quote.latest_version?.payload_json as Record<string, unknown> | undefined;
  const dimsRaw = Array.isArray(payload?.dimensions)
    ? payload?.dimensions
    : Array.isArray((payload?.shipment as Record<string, unknown> | undefined)?.pieces)
      ? ((payload?.shipment as Record<string, unknown>).pieces as unknown[])
      : [];

  let pieces = 0;
  let totalActual = 0;
  let totalVolumetric = 0;

  for (const piece of dimsRaw) {
    const dim = piece as Record<string, unknown>;
    const pcs = Number(dim.pieces || 0);
    const l = Number(dim.length_cm || 0);
    const w = Number(dim.width_cm || 0);
    const h = Number(dim.height_cm || 0);
    const kg = Number(dim.gross_weight_kg || 0);

    pieces += pcs;
    totalActual += kg * pcs;
    if (l > 0 && w > 0 && h > 0) {
      totalVolumetric += (l * w * h / 6000) * pcs;
    }
  }

  if (totalActual <= 0) {
    const payloadTotal =
      payload && "total_weight_kg" in payload
        ? Number(payload.total_weight_kg || 0)
        : payload && payload.shipment && typeof payload.shipment === "object" && "total_weight_kg" in (payload.shipment as Record<string, unknown>)
          ? Number(((payload.shipment as Record<string, unknown>).total_weight_kg as string | number) || 0)
          : 0;
    const versionTotal = Number(quote.latest_version?.total_weight_kg || 0);
    totalActual = Math.max(payloadTotal, versionTotal, 0);
  }

  const chargeableWeight = Math.ceil(Math.max(totalActual, totalVolumetric, 0));

  return {
    pieces: Math.max(pieces, 0),
    totalWeightKg: Math.ceil(totalActual),
    volumetricWeightKg: Math.ceil(totalVolumetric),
    chargeableWeightKg: chargeableWeight,
  };
}

export function computeChargeableWeight(quote: V3QuoteComputeResponse) {
  const shipmentMetrics = computeShipmentMetrics(quote);
  const fallbackPieces = quote.latest_version?.payload_json && "pieces" in quote.latest_version.payload_json
    ? Number((quote.latest_version.payload_json as Record<string, unknown>).pieces || 0)
    : 0;

  return {
    pieces: shipmentMetrics.pieces > 0 ? shipmentMetrics.pieces : Math.max(fallbackPieces, 1),
    chargeableWeight: shipmentMetrics.chargeableWeightKg > 0 ? shipmentMetrics.chargeableWeightKg : 1,
  };
}

export function buildSpotResumeContext(quote: V3QuoteComputeResponse): SpotResumeContext {
  const request = (quote.request_details_json || {}) as Record<string, unknown>;
  const payload = (quote.latest_version?.payload_json || {}) as Record<string, unknown>;
  const shipment = (payload.shipment || {}) as Record<string, unknown>;
  const weightInfo = computeChargeableWeight(quote);

  const originCode = normalizeAirportCode(
    payload.origin_airport,
    request.origin_airport,
    shipment.origin_airport,
    quote.origin_location,
  );
  const destinationCode = normalizeAirportCode(
    payload.destination_airport,
    request.destination_airport,
    shipment.destination_airport,
    quote.destination_location,
  );
  const originCountry = normalizeCountryCode(
    payload.origin_country,
    request.origin_country,
    shipment.origin_country,
    originCode,
  );
  const destinationCountry = normalizeCountryCode(
    payload.destination_country,
    request.destination_country,
    shipment.destination_country,
    destinationCode,
  );
  const commodity = String(
    payload.commodity_code ||
    request.commodity_code ||
    shipment.commodity_code ||
    "GCR",
  ).toUpperCase() as SPECommodity;

  return {
    originCode,
    destinationCode,
    originCountry,
    destinationCountry,
    commodity,
    serviceScope: String(quote.service_scope || payload.service_scope || request.service_scope || "D2D").toUpperCase(),
    paymentTerm: String(quote.payment_term || payload.payment_term || request.payment_term || "PREPAID").toUpperCase() === "COLLECT"
      ? "COLLECT"
      : "PREPAID",
    chargeableWeight: weightInfo.chargeableWeight,
    pieces: weightInfo.pieces,
    outputCurrency: String(quote.output_currency || payload.output_currency || request.output_currency || "PGK").toUpperCase(),
    shipmentType: String(quote.shipment_type || request.shipment_type || "EXPORT").toUpperCase(),
    customerId: typeof request.customer_id === "string" ? request.customer_id : null,
    customerName: getCustomerName(quote.customer),
  };
}

export function buildFxEntries(
  quote: V3QuoteComputeResponse,
  computeResult: QuoteComputeResult | null
): Array<[string, string]> {
  const relevantCurrencies = new Set<string>();
  const addCurrency = (currency: string | null | undefined) => {
    if (!currency) return;
    const code = currency.toUpperCase().trim();
    if (!code || code === "PGK") return;
    relevantCurrencies.add(code);
  };

  addCurrency(quote.output_currency);
  addCurrency(quote.latest_version?.totals?.currency);
  addCurrency(computeResult?.totals?.currency);

  quote.latest_version?.lines?.forEach((line) => {
    addCurrency(line.cost_fcy_currency);
    addCurrency(line.sell_fcy_currency);
  });
  computeResult?.buy_lines?.forEach((line) => addCurrency(line.currency));
  computeResult?.sell_lines?.forEach((line) => addCurrency(line.sell_currency));

  const rates: Record<string, string> = {
    ...(computeResult?.exchange_rates || {}),
  };

  if (Object.keys(rates).length === 0) {
    for (const line of quote.latest_version?.lines || []) {
      const rate = line.exchange_rate;
      if (!rate) continue;
      const ccy = (line.sell_fcy_currency || line.cost_fcy_currency || "").toUpperCase();
      if (!ccy || ccy === "PGK") continue;
      rates[`${ccy}/PGK`] = String(rate);
    }
  }

  if (Object.keys(rates).length === 0) {
    const sums: Record<string, { fcy: number; pgk: number }> = {};
    const add = (currency: string | null | undefined, fcyRaw: string | null | undefined, pgkRaw: string | null | undefined) => {
      const ccy = (currency || "").toUpperCase().trim();
      if (!ccy || ccy === "PGK") return;
      const fcy = Number(fcyRaw || 0);
      const pgk = Number(pgkRaw || 0);
      if (!Number.isFinite(fcy) || !Number.isFinite(pgk) || fcy <= 0 || pgk <= 0) return;
      if (!sums[ccy]) sums[ccy] = { fcy: 0, pgk: 0 };
      sums[ccy].fcy += fcy;
      sums[ccy].pgk += pgk;
    };

    for (const line of quote.latest_version?.lines || []) {
      add(line.sell_fcy_currency, line.sell_fcy, line.sell_pgk);
    }
    for (const line of computeResult?.sell_lines || []) {
      add(line.sell_currency, line.sell_fcy, line.sell_pgk);
    }

    for (const [ccy, totals] of Object.entries(sums)) {
      if (totals.fcy > 0 && totals.pgk > 0) {
        rates[`${ccy}/PGK`] = (totals.pgk / totals.fcy).toFixed(6);
      }
    }
  }

  if (Object.keys(rates).length === 0) {
    const displayCurrency =
      computeResult?.totals?.currency ||
      quote.latest_version?.totals?.currency ||
      quote.output_currency ||
      "PGK";

    const totalFcy = Number(
      computeResult?.totals?.total_sell_fcy ||
      quote.latest_version?.totals?.total_sell_fcy ||
      0
    );
    const totalPgk = Number(
      computeResult?.totals?.sell_pgk ||
      quote.latest_version?.totals?.total_sell_pgk ||
      0
    );

    if (displayCurrency.toUpperCase() !== "PGK" && totalFcy > 0 && totalPgk > 0) {
      rates[`${displayCurrency.toUpperCase()}/PGK`] = (totalPgk / totalFcy).toFixed(6);
    }
  }

  let visible = Object.entries(rates).filter(([key]) => {
    const upper = key.toUpperCase();
    if (relevantCurrencies.has(upper)) return true;
    for (const code of Array.from(relevantCurrencies)) {
      if (upper.includes(`${code}/`) || upper.includes(`/${code}`) || upper.includes(code)) {
        return true;
      }
    }
    return false;
  });

  if (visible.length === 0 && relevantCurrencies.size > 0) {
    visible = Object.entries(rates).filter(([key]) => {
      const upper = key.toUpperCase();
      return upper !== "PGK" && upper !== "BASE_CURRENCY";
    });
  }

  const sorted = visible.sort((a, b) => a[0].localeCompare(b[0]));
  return sorted;
}
