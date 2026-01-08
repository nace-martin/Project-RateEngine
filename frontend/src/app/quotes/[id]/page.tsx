"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { getQuoteV3, getQuoteCompute, downloadQuotePDF } from "@/lib/api";
import {
  V3QuoteComputeResponse,
  QuoteComputeResult,
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
import { Loader2, ChevronRight, ArrowLeft, CheckCircle } from "lucide-react";
import { QuoteStatusBadge, QuoteStatusActions } from "@/components/QuoteStatusBadge";

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

  const isIncomplete = quote.status === "INCOMPLETE";
  const canDownloadPDF = quote.status === "FINALIZED" || quote.status === "SENT";

  return (
    <div className="container mx-auto max-w-6xl px-4 py-6 space-y-6">
      {/* Breadcrumb Navigation */}
      <nav className="flex items-center gap-2 text-sm text-slate-500">
        <Link href="/quotes" className="hover:text-slate-700 transition-colors">
          Quotes
        </Link>
        <ChevronRight className="w-4 h-4" />
        <span className="text-slate-400">New Quote</span>
        <ChevronRight className="w-4 h-4" />
        <span className="font-medium text-slate-700">Finalize</span>
      </nav>

      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-slate-900">
              {quote.quote_number}
            </h1>
            <QuoteStatusBadge status={quote.status} size="default" />
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
          <Button
            variant="outline"
            onClick={() => {
              // Check if this is a spot quote derived from an envelope
              const payloadJson = quote.latest_version?.payload_json;
              const speId = payloadJson ? (payloadJson as unknown as { spot_envelope_id?: string }).spot_envelope_id : undefined;
              if (speId) {
                router.push(`/quotes/spot/${speId}`);
              } else {
                router.push(`/quotes/new?edit=${quote.id}`);
              }
            }}
            className="gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Edit
          </Button>
          <QuoteStatusActions
            quoteId={quote.id}
            status={quote.status}
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
                {quote.latest_version?.totals?.currency || 'PGK'} {parseFloat(quote.latest_version?.totals?.total_sell_fcy_incl_gst || quote.latest_version?.totals?.total_sell_pgk_incl_gst || "0").toLocaleString()}
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
            {quote.status === "FINALIZED" || quote.status === "SENT" ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <CheckCircle className="h-4 w-4 text-emerald-600" />
                <span>Quote {quote.status.toLowerCase()}</span>
              </div>
            ) : quote.status === "DRAFT" ? (
              <QuoteStatusActions
                quoteId={quote.id}
                status={quote.status}
                hasMissingRates={quote.latest_version?.totals?.has_missing_rates || false}
                onStatusChange={() => {
                  getQuoteV3(id).then((data) => setQuote(data));
                }}
              />
            ) : null}
          </div>
        </div>
      </div>

    </div>
  );
}

