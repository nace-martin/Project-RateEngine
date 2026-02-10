"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { getQuoteV3, getQuoteCompute, downloadQuotePDF, transitionQuoteStatus } from "@/lib/api";
import {
  V3QuoteComputeResponse,
  QuoteComputeResult,
  V3DimensionInput,
} from "@/lib/types";
import QuoteResultDisplay from "@/components/QuoteResultDisplay";
import QuoteFinancialBreakdown from "@/components/QuoteFinancialBreakdown";
import QuoteSettings from "@/components/QuoteSettings";
import RoutingWarning from "@/components/RoutingWarning";
import { BucketSourcingView } from "@/components/pricing/BucketSourcingView";
import { SpotChargeResultDisplay } from "@/components/pricing/SpotChargeResultDisplay";
import { getSpotChargesForQuote } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, ChevronRight, ArrowLeft, CheckCircle, CheckCircle2, Pencil, ArrowRight } from "lucide-react";
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
  const [hasSpotCharges, setHasSpotCharges] = useState(false);
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

          // Check if quote has spot charges
          try {
            const spotCharges = await getSpotChargesForQuote(id);
            const totalLines = spotCharges.charges.ORIGIN.length +
              spotCharges.charges.FREIGHT.length +
              spotCharges.charges.DESTINATION.length;
            setHasSpotCharges(totalLines > 0);
          } catch {
            setHasSpotCharges(false);
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

            <AlertDescription className="grid grid-cols-1 md:grid-cols-4 gap-4 text-sm mt-1">
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
                  {(() => {
                    if (!computeResult?.exchange_rates) return <span className="text-slate-400 italic">N/A</span>;

                    const relevantCurrencies = new Set<string>();

                    // Helper to safely add currency
                    const addCurrency = (c: string | null | undefined) => {
                      if (c && c.toUpperCase() !== 'PGK' && c.trim() !== '') {
                        relevantCurrencies.add(c.toUpperCase());
                      }
                    };

                    // 1. Output Currency
                    addCurrency(quote.output_currency);
                    addCurrency(quote.latest_version?.totals?.currency);
                    addCurrency(computeResult.totals?.currency);

                    // 2. Lines from latest_version (Stored State)
                    quote.latest_version?.lines?.forEach(line => {
                      addCurrency(line.cost_fcy_currency);
                      addCurrency(line.sell_fcy_currency);
                    });

                    // 3. Lines from computeResult (Calculated State)
                    computeResult.buy_lines?.forEach(line => addCurrency(line.currency));
                    computeResult.sell_lines?.forEach(line => addCurrency(line.sell_currency));

                    // Filter rates that match relevant currencies
                    const ratesToShow = Object.entries(computeResult.exchange_rates).filter(([key]) => {
                      const upperKey = key.toUpperCase();
                      // If key is exactly one of the relevant currencies (e.g. "AUD")
                      if (relevantCurrencies.has(upperKey)) return true;

                      // If key is a pair containing one of the relevant currencies (e.g. "AUD/PGK")
                      for (const code of Array.from(relevantCurrencies)) {
                        if (upperKey.includes(`${code}/`) || upperKey.includes(`/${code}`)) return true;
                        if (upperKey.includes(code)) return true; // Broad match fallback
                      }
                      return false;
                    });

                    if (ratesToShow.length === 0) {
                      // If we have rates but filtered them all out, it implies everything is PGK.
                      // But usually we shouldn't be here if there are foreign currencies involved.
                      // Check if we actually found relevant currencies
                      if (relevantCurrencies.size === 0) {
                        // User feedback: "if app is converting AUD to PGK then I want that particular FX rate"
                        // If we didn't find "AUD" in the lines, then we missed it.
                        // Fallback: show ALL rates if no foreign currency detected but exchange rates exist?
                        // No, user specifically said "not all".
                        // Let's assume if it says "Base (PGK)" it's because the data doesn't have the currency tag.
                        return <span className="text-slate-400 italic">Base (PGK)</span>;
                      }
                      return <span className="text-slate-400 italic">None</span>;
                    }

                    // Sort to put pairs first if possible, or just standard sort
                    return ratesToShow.sort().map(([currency, rate]) => (
                      <div key={currency}>{currency}: {rate}</div>
                    ));
                  })()}
                </div>
              </div>

              {/* Chargeable Weight */}
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">Total Weight</p>
                <p className="font-medium text-slate-900">
                  {/* Calculate Gross Weight from payload */}
                  {(() => {
                    const dims = quote.latest_version?.payload_json?.dimensions || [];
                    const totalKg = dims.reduce((sum: number, d: V3DimensionInput) => {
                      const pcs = d.pieces || 1;
                      const weight = parseFloat(d.gross_weight_kg || "0");
                      return sum + (weight * pcs);
                    }, 0);
                    return totalKg > 0 ? `${totalKg.toLocaleString()} kg` : "0 kg";
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
          <BucketSourcingView
            quote={quote}
            onFinalizeSuccess={() => {
              // Refresh the quote data and spot charges state after finalization
              getQuoteV3(id).then((data) => {
                setQuote(data);
                setHasSpotCharges(true); // Mark as having spot charges
              });
            }}
          />
        ) : (
          /* Two-Column Layout for Finalized Quotes */
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column - Financial Breakdown (2/3 width) */}
            <div className="lg:col-span-2 space-y-6">
              {hasSpotCharges ? (
                <SpotChargeResultDisplay quote={quote} />
              ) : computeResult ? (
                <QuoteFinancialBreakdown result={computeResult} />
              ) : (
                <QuoteResultDisplay quote={quote} />
              )}
            </div>

            {/* Right Column - Document Preview & Settings (1/3 width) */}
            <div className="space-y-6">
              <QuoteSettings defaultPaymentTerm={quote.payment_term?.toLowerCase()} />
            </div>
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
