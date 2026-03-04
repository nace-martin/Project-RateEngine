"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import {
  createSpotEnvelope,
  evaluateSpotTrigger,
  getQuoteV3,
  getQuoteCompute,
  downloadQuotePDF,
  transitionQuoteStatus,
  validateSpotScope,
} from "@/lib/api";
import {
  V3QuoteComputeResponse,
  QuoteComputeResult,
} from "@/lib/types";
import QuoteFinancialBreakdown from "@/components/QuoteFinancialBreakdown";

import RoutingWarning from "@/components/RoutingWarning";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, ArrowLeft, CheckCircle, CheckCircle2, Pencil, ArrowRight } from "lucide-react";
import { QuoteStatusBadge, QuoteStatusActions } from "@/components/QuoteStatusBadge";
import { getCustomerName, getEffectiveQuoteStatus } from "@/lib/quote-helpers";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

export default function QuoteDetailPage() {
  const { user } = useAuth();
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [quote, setQuote] = useState<V3QuoteComputeResponse | null>(null);
  const [computeResult, setComputeResult] = useState<QuoteComputeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfDownloading, setPdfDownloading] = useState(false);

  useEffect(() => {
    if (id && user) {
      const fetchQuote = async () => {
        setLoading(true);
        setError(null);
        try {
          // Use the new V3 API function
          const data = await getQuoteV3(id);
          setQuote(data);

          // Fetch compute result (ChargeEngine)
          try {
            const computeData = await getQuoteCompute(id);
            setComputeResult(computeData);
          } catch (computeErr) {
            console.error("Failed to fetch compute result:", computeErr);
          }

        } catch (err: unknown) {
          const message =
            err instanceof Error ? err.message : "An unexpected error occurred.";
          setError(message);
        } finally {
          setLoading(false);
        }
      };
      fetchQuote();
    }
  }, [id, user]);


  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="mr-2 h-8 w-8 animate-spin" />
        <span>Loading quote...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto max-w-6xl p-4">
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!quote) {
    return (
      <div className="container mx-auto max-w-6xl p-4">
        <Alert variant="default">
          <AlertTitle>No Quote Found</AlertTitle>
          <AlertDescription>
            The quote you are looking for does not exist.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const effectiveStatus = getEffectiveQuoteStatus(quote.status, quote.valid_until);
  const isIncomplete = effectiveStatus === "INCOMPLETE";
  const isArchived = quote.is_archived;
  const canDownloadPDF = (effectiveStatus === "FINALIZED" || effectiveStatus === "SENT");
  const displayTotals = computeResult?.totals ?? quote.latest_version?.totals;
  const displayCurrency =
    displayTotals?.currency ||
    quote.latest_version?.totals?.total_sell_fcy_currency ||
    "PGK";
  const displayAmount =
    displayTotals?.total_sell_fcy_incl_gst ||
    displayTotals?.sell_pgk_incl_gst ||
    quote.latest_version?.totals?.total_sell_fcy_incl_gst ||
    quote.latest_version?.totals?.total_sell_pgk_incl_gst ||
    "0";
  const shipmentMetrics = computeShipmentMetrics(quote);
  const fxEntries = buildFxEntries(quote, computeResult);

  return (
    <div className="container mx-auto max-w-6xl px-4 py-6 space-y-6">
      {/* Archival Warning */}
      {isArchived && (
        <Alert variant="destructive" className="bg-amber-50 border-amber-200 text-amber-900">
          <AlertTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            Archived Quote
          </AlertTitle>
          <AlertDescription>
            This quote has been archived and is read-only. RESTORATION is required to edit.
          </AlertDescription>
        </Alert>
      )}

      {/* Breadcrumb Navigation */}
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/dashboard">Dashboard</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbLink href="/quotes">Quotes</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{quote.quote_number}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-slate-900">
              {quote.quote_number}
            </h1>
            <QuoteStatusBadge status={effectiveStatus} size="default" />
            {isArchived && <span className="px-2 py-1 text-xs font-semibold bg-gray-100 text-gray-600 rounded">ARCHIVED</span>}
          </div>
          <p className="text-sm text-slate-500">
            Created on {new Date(quote.created_at).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'short',
              day: 'numeric'
            })} • {quote.shipment_type} Air Freight
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Only show Back to Edit for editable quotes */}
          {(!isArchived && (effectiveStatus === "DRAFT" || effectiveStatus === "INCOMPLETE")) && (
            <Button
              variant="outline"
              onClick={() => {
                if (quote.shipment_type === "SPOT_NEGOTIATION" && quote.spot_negotiation) {
                  // For spot, we might still want to go to spot details
                  // But if it's a standard quote stored in our system, we should support edit
                  // Assuming we map spot ID somewhere?
                  // The original code: router.push(`/quotes/spot/${speId}`);
                  // We need to keep that logic if possible
                  const speId = quote.spot_negotiation.id;
                  router.push(`/quotes/spot/${speId}`);
                } else {
                  router.push(`/quotes/${quote.id}/edit`);
                }
              }}
              className="gap-2"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Edit
            </Button>
          )}
          <QuoteStatusActions
            quoteId={quote.id}
            status={quote.status}
            validUntil={quote.valid_until}
            hasMissingRates={quote.latest_version?.totals?.has_missing_rates || false}
            onStatusChange={() => {
              getQuoteV3(id).then((data) => setQuote(data));
            }}
          />
        </div>
      </div>

      {/* Scrollable Content Area with bottom padding for footer */}
      <div className="pb-32 space-y-6">
        {/* Summary Bar - Condensed/Hidden on Scroll if we wanted, but let's keep it simply or remove if redundant */}
        {/* QuoteSummaryBar quote={quote}  <-- REMOVED since we have sticky footer now */}

        {/* --- INTERNAL USE ONLY: AGENT & WEIGHT VISIBILITY --- */}
        <div className="md:col-span-1">
          <Alert className="bg-slate-50 border-slate-200 shadow-sm relative overflow-hidden">
            {/* "Internal Only" Badge */}
            <div className="absolute top-0 right-0 bg-slate-200 text-slate-600 text-[10px] font-bold px-2 py-0.5 rounded-bl">
              INTERNAL USE ONLY
            </div>

            <AlertDescription className="grid grid-cols-2 lg:grid-cols-5 gap-4 text-sm mt-1">
              {/* Customer */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Customer</p>
                <p className="font-medium text-slate-900 truncate" title={getCustomerName(quote.customer)}>
                  {getCustomerName(quote.customer)}
                </p>
              </div>

              {/* Sales Rep */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Sales Rep</p>
                <p className="font-medium text-slate-900">
                  {quote.created_by || <span className="text-slate-400 italic">Unassigned</span>}
                </p>
              </div>

              {/* Rate Provider */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Rate Provider</p>
                <p className="font-medium text-slate-900 truncate" title={quote.rate_provider || "Internal"}>
                  {quote.rate_provider || <span className="text-slate-400 italic">Internal</span>}
                </p>
              </div>

              {/* Routing */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Routing</p>
                <div className="font-medium text-slate-900 flex items-center gap-1">
                  <span>{quote.origin_location?.split('-')[0] || quote.origin_location}</span>
                  <ArrowRight className="h-3 w-3" />
                  <span>{quote.destination_location?.split('-')[0] || quote.destination_location}</span>
                </div>
              </div>

              {/* FX Rate */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">FX Rate</p>
                <div className="font-medium text-slate-900 text-xs">
                  {fxEntries.length > 0 ? (
                    fxEntries.map(([currency, rate]) => (
                      <div key={currency}>{currency}: {String(rate)}</div>
                    ))
                  ) : (
                    <span className="text-slate-400 italic">Base (PGK)</span>
                  )}
                </div>
              </div>

              {/* Total Weight */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Total Weight</p>
                <p className="font-medium text-slate-900">
                  {shipmentMetrics.totalWeightKg > 0
                    ? `${shipmentMetrics.totalWeightKg.toLocaleString()} kg`
                    : "0 kg"}
                </p>
              </div>

              {/* Volumetric Weight */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Volumetric Weight</p>
                <p className="font-medium text-slate-900">
                  {shipmentMetrics.volumetricWeightKg > 0
                    ? `${shipmentMetrics.volumetricWeightKg.toLocaleString()} kg`
                    : "0 kg"}
                </p>
              </div>

              {/* Chargeable Weight (CW) */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Chargeable Weight (CW)</p>
                <p className="font-medium text-slate-900">
                  {shipmentMetrics.chargeableWeightKg > 0
                    ? `${shipmentMetrics.chargeableWeightKg.toLocaleString()} kg`
                    : "0 kg"}
                </p>
              </div>

              {/* Validity */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Validity</p>
                <p className="font-medium text-slate-900">
                  7 Days
                </p>
              </div>

              {/* Payment Terms */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Payment Terms</p>
                <p className="font-medium text-slate-900">
                  {(() => {
                    const term = (quote.payment_term || "Collect").toLowerCase();
                    return term === 'credit' ? 'Credit (30 Days)' : term.charAt(0).toUpperCase() + term.slice(1);
                  })()}
                </p>
              </div>
            </AlertDescription>
          </Alert>
        </div>

        {/* Display routing warning if VIA routing is required */}
        {computeResult?.routing && (
          <RoutingWarning routingInfo={computeResult.routing} />
        )}

        {/* Main Content Area */}
        {isIncomplete ? (
          <SpotNegotiationCard quote={quote} />
        ) : (
          /* Full-width Layout for Finalized Quotes */
          <div className="space-y-6">
            {computeResult ? (
              <QuoteFinancialBreakdown result={computeResult} />
            ) : (
              <QuoteFinancialBreakdown result={quote} />
            )}
          </div>
        )}
      </div>

      {/* Sticky Footer Action Bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] z-50">
        <div className="container mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div>
              <p className="text-xs text-slate-500 uppercase font-semibold">Total Estimated Cost</p>
              <p className="text-2xl font-bold text-slate-900">
                {displayCurrency} {parseFloat(displayAmount).toLocaleString()}
              </p>
              <p className="text-[10px] text-slate-400">
                Inc. GST
              </p>
            </div>
            {/* Currency Exchange Badge placeholder (future task) */}
            {quote.latest_version?.totals?.currency !== 'PGK' && (
              <div className="hidden md:block px-3 py-1 bg-amber-50 rounded border border-amber-100 text-xs text-amber-700">
                <strong>Note:</strong> Pricing in {quote.latest_version?.totals?.currency}
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            {canDownloadPDF && (
              <Button
                variant="outline"
                className="hidden sm:flex"
                disabled={pdfDownloading}
                onClick={async () => {
                  setPdfDownloading(true);
                  try {
                    await downloadQuotePDF(quote.id, quote.quote_number);
                    if (quote.status?.toUpperCase?.() === "FINALIZED") {
                      const sendResult = await transitionQuoteStatus(quote.id, "send");
                      if (sendResult.success) {
                        const refreshed = await getQuoteV3(id);
                        setQuote(refreshed);
                      } else {
                        console.error("Auto-send failed:", sendResult.error);
                      }
                    }
                  } catch (err) {
                    console.error("PDF download failed:", err);
                    alert(err instanceof Error ? err.message : "Failed to download PDF");
                  } finally {
                    setPdfDownloading(false);
                  }
                }}
              >
                {pdfDownloading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Generating...
                  </>
                ) : (
                  "Download PDF"
                )}
              </Button>
            )}
            {/* Only show finalize button for DRAFT quotes, handled by QuoteStatusActions above */}
            {effectiveStatus === "FINALIZED" || effectiveStatus === "SENT" || effectiveStatus === "EXPIRED" ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <CheckCircle className="h-4 w-4 text-emerald-600" />
                <span>Quote {effectiveStatus.toLowerCase()}</span>
              </div>
            ) : effectiveStatus === "DRAFT" ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2 mr-2 hidden sm:flex"
                  onClick={() => {
                    if (quote.shipment_type === "SPOT_NEGOTIATION" && quote.spot_negotiation) {
                      router.push(`/quotes/spot/${quote.spot_negotiation.id}`);
                    } else {
                      router.push(`/quotes/${quote.id}/edit`);
                    }
                  }}
                >
                  <Pencil className="h-4 w-4" />
                  Edit Quote
                </Button>
                <QuoteStatusActions
                  quoteId={quote.id}
                  status={quote.status}
                  validUntil={quote.valid_until}
                  hasMissingRates={quote.latest_version?.totals?.has_missing_rates || false}
                  showDelete={false}
                  onStatusChange={() => {
                    getQuoteV3(id).then((data) => setQuote(data));
                  }}
                />
              </>
            ) : null}
          </div>
        </div>
      </div>

    </div >
  );
}

function SpotNegotiationCard({ quote }: { quote: V3QuoteComputeResponse }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleOpenSpot = async () => {
    setError(null);
    setLoading(true);
    try {
      const existingSpeId =
        quote.spot_negotiation?.id || readSpotEnvelopeId(quote.id);
      if (existingSpeId) {
        router.push(`/quotes/spot/${existingSpeId}`);
        return;
      }

      const originLocation = quote.origin_location;
      const destinationLocation = quote.destination_location;

      const originCode =
        extractIataCode(originLocation) ||
        (quote.latest_version?.payload_json?.origin_airport || "").toUpperCase();
      const destinationCode =
        extractIataCode(destinationLocation) ||
        (quote.latest_version?.payload_json?.destination_airport || "").toUpperCase();
      const originCountry = extractCountryCode(originLocation, originCode) || "OTHER";
      const destinationCountry = extractCountryCode(destinationLocation, destinationCode) || "OTHER";

      const weightInfo = computeChargeableWeight(quote);
      const commodity =
        quote.latest_version?.payload_json?.is_dangerous_goods ? "DG" : "GCR";

      const scopeCheck = await validateSpotScope({
        origin_country: originCountry,
        destination_country: destinationCountry,
        origin_code: originCode || "",
        destination_code: destinationCode || "",
      });
      if (!scopeCheck.is_valid) {
        throw new Error(scopeCheck.error || "Shipment is out of SPOT scope.");
      }

      const triggerResult = await evaluateSpotTrigger({
        origin_country: originCountry,
        destination_country: destinationCountry,
        commodity,
        origin_airport: originCode || "",
        destination_airport: destinationCode || "",
        has_valid_buy_rate: false,
        service_scope: quote.service_scope,
      });

      const triggerCode = triggerResult.trigger?.code || "MISSING_RATES";
      const triggerText =
        triggerResult.trigger?.text || "Missing rates require manual sourcing.";

      const spe = await createSpotEnvelope({
        shipment_context: {
          origin_country: originCountry,
          destination_country: destinationCountry,
          origin_code: originCode || "",
          destination_code: destinationCode || "",
          commodity,
          total_weight_kg: weightInfo.chargeableWeight,
          pieces: weightInfo.pieces,
          service_scope: (quote.service_scope || "P2P").toLowerCase(),
          missing_components: triggerResult.trigger?.missing_components,
        },
        charges: [],
        trigger_code: triggerCode,
        trigger_text: triggerText,
        conditions: { rate_validity_hours: 72 },
        quote_id: quote.id,
      });

      if (spe?.id) {
        storeSpotEnvelopeId(quote.id, spe.id);
      }

      const params = new URLSearchParams({
        origin_country: originCountry,
        dest_country: destinationCountry,
        origin_code: originCode || "",
        dest_code: destinationCode || "",
        commodity,
        weight: String(weightInfo.chargeableWeight),
        pieces: String(weightInfo.pieces),
        trigger_code: triggerCode,
        trigger_text: triggerText,
        service_scope: quote.service_scope,
        payment_term: quote.payment_term,
        output_currency: quote.output_currency || "PGK",
        shipment_type: quote.shipment_type,
      });
      if (triggerResult.trigger?.missing_components?.length) {
        params.append("missing_components", triggerResult.trigger.missing_components.join(","));
      }

      router.push(`/quotes/spot/${spe.id}?${params.toString()}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to open SPOT flow.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-amber-200 bg-amber-50/40">
      <CardHeader>
        <CardTitle className="text-lg text-amber-800">SPOT Rate Required</CardTitle>
        <CardDescription>
          This quote has missing rates. Continue in the SPOT workflow to source
          agent pricing and finalize the quote.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          We will open the SPOT envelope flow for this shipment.
        </div>
        <Button onClick={handleOpenSpot} disabled={loading}>
          {loading ? "Opening..." : "Open SPOT Workflow"}
        </Button>
      </CardContent>
      {error && (
        <CardContent className="pt-0">
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </CardContent>
      )}
    </Card>
  );
}

const SPOT_ENVELOPE_STORAGE_KEY = "spotEnvelopeByQuoteId";

function readSpotEnvelopeId(quoteId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SPOT_ENVELOPE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, string>;
    return parsed[quoteId] || null;
  } catch {
    return null;
  }
}

function storeSpotEnvelopeId(quoteId: string, speId: string) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(SPOT_ENVELOPE_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    parsed[quoteId] = speId;
    window.localStorage.setItem(SPOT_ENVELOPE_STORAGE_KEY, JSON.stringify(parsed));
  } catch {
    // Ignore storage errors
  }
}

function extractIataCode(location?: string): string | undefined {
  if (!location) return undefined;
  const iataMatch = location.match(/\(([A-Z]{3})\)/i);
  if (iataMatch) return iataMatch[1].toUpperCase();
  const prefixMatch = location.match(/^([A-Z]{3})(?:\s*[-,/]|$)/i);
  if (prefixMatch) return prefixMatch[1].toUpperCase();
  const trimmed = location.trim();
  if (trimmed.length === 3) return trimmed.toUpperCase();
  return undefined;
}

function extractCountryCode(location?: string, iataCode?: string): string | undefined {
  if (!location) return undefined;
  const countryMatch = location.match(/,\s*([A-Z]{2})\s*$/i);
  if (countryMatch) return countryMatch[1].toUpperCase();

  const airportCountryMap: Record<string, string> = {
    BNE: "AU", SYD: "AU", MEL: "AU", PER: "AU", ADL: "AU", CBR: "AU",
    DRW: "AU", CNS: "AU", OOL: "AU", HBA: "AU",
    LAX: "US", JFK: "US", SFO: "US", ORD: "US", MIA: "US", DFW: "US",
    ATL: "US", SEA: "US", DEN: "US",
    PVG: "CN", PEK: "CN", CAN: "CN", SZX: "CN", CTU: "CN",
    HKG: "HK",
    SIN: "SG",
    AKL: "NZ", WLG: "NZ", CHC: "NZ",
    LHR: "GB", LGW: "GB", MAN: "GB", STN: "GB",
    POM: "PG", LAE: "PG",
    NRT: "JP", HND: "JP", KIX: "JP",
    ICN: "KR", GMP: "KR",
    BKK: "TH", DMK: "TH",
    KUL: "MY",
    CGK: "ID", DPS: "ID",
    MNL: "PH", CEB: "PH",
    DEL: "IN", BOM: "IN", BLR: "IN",
    DXB: "AE", AUH: "AE",
  };
  const code = iataCode || extractIataCode(location);
  return code ? airportCountryMap[code] : undefined;
}

function computeChargeableWeight(quote: V3QuoteComputeResponse) {
  const shipmentMetrics = computeShipmentMetrics(quote);
  const fallbackPieces = quote.latest_version?.payload_json && "pieces" in quote.latest_version.payload_json
    ? Number((quote.latest_version.payload_json as Record<string, unknown>).pieces || 0)
    : 0;

  return {
    pieces: shipmentMetrics.pieces > 0 ? shipmentMetrics.pieces : Math.max(fallbackPieces, 1),
    chargeableWeight: shipmentMetrics.chargeableWeightKg > 0 ? shipmentMetrics.chargeableWeightKg : 1,
  };
}

function computeShipmentMetrics(quote: V3QuoteComputeResponse) {
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

function buildFxEntries(
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

  // Fallback for legacy/spot paths where compute_v3 returns empty exchange_rates.
  if (Object.keys(rates).length === 0) {
    for (const line of quote.latest_version?.lines || []) {
      const rate = line.exchange_rate;
      if (!rate) continue;
      const ccy = (line.sell_fcy_currency || line.cost_fcy_currency || "").toUpperCase();
      if (!ccy || ccy === "PGK") continue;
      rates[`${ccy}/PGK`] = String(rate);
    }
  }

  // Fallback when explicit FX lines are absent but quote is in non-PGK output.
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
  if (sorted.length > 0) return sorted;
  return [["PGK/PGK", "1.000000"]];
}
