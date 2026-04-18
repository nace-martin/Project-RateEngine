"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import {
  getQuoteV3,
  getQuoteCompute,
  downloadQuotePDF,
  transitionQuoteStatus,
  createSpotEnvelope,
  evaluateSpotTrigger,
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
import { formatServiceScope } from "@/lib/display";
import { getCustomerName, getEffectiveQuoteStatus } from "@/lib/quote-helpers";
import type { SPECommodity, TriggerResult } from "@/lib/spot-types";
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
  const [spotLaunching, setSpotLaunching] = useState(false);
  const [spotLaunchError, setSpotLaunchError] = useState<string | null>(null);
  const [spotTriggerResult, setSpotTriggerResult] = useState<TriggerResult | null>(null);
  const [spotTriggerChecking, setSpotTriggerChecking] = useState(false);
  const [spotTriggerChecked, setSpotTriggerChecked] = useState(false);
  const [spotTriggerCheckError, setSpotTriggerCheckError] = useState<string | null>(null);
  const redirectingSpotRef = useRef(false);
  const spotWorkflowHref = (() => {
    if (!quote) return null;
    const currentStatus = getEffectiveQuoteStatus(quote.status, quote.valid_until);
    if (currentStatus !== "INCOMPLETE") return null;
    const existingSpotEnvelopeId = quote.spot_negotiation?.id;
    if (!existingSpotEnvelopeId) return null;
    const params = buildSpotWorkflowParams(quote);
    params.set("returnTo", `/quotes/${quote.id}`);
    return `/quotes/spot/${existingSpotEnvelopeId}?${params.toString()}`;
  })();

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

  useEffect(() => {
    if (!spotWorkflowHref || redirectingSpotRef.current) {
      return;
    }
    redirectingSpotRef.current = true;
    router.replace(spotWorkflowHref);
  }, [router, spotWorkflowHref]);

  useEffect(() => {
    if (!quote) {
      setSpotTriggerResult(null);
      setSpotTriggerChecking(false);
      setSpotTriggerChecked(false);
      setSpotTriggerCheckError(null);
      return;
    }

    const currentStatus = getEffectiveQuoteStatus(quote.status, quote.valid_until);
    if (currentStatus !== "INCOMPLETE" || quote.spot_negotiation?.id) {
      setSpotTriggerResult(null);
      setSpotTriggerChecking(false);
      setSpotTriggerChecked(false);
      setSpotTriggerCheckError(null);
      return;
    }

    let cancelled = false;

    const checkSpotTrigger = async () => {
      setSpotTriggerChecking(true);
      setSpotTriggerChecked(false);
      setSpotTriggerCheckError(null);
      try {
        const result = await evaluateLatestSpotTrigger(quote);
        if (cancelled) {
          return;
        }
        setSpotTriggerResult(result.trigger ?? null);
      } catch (err) {
        if (cancelled) {
          return;
        }
        setSpotTriggerResult(null);
        setSpotTriggerCheckError(
          err instanceof Error ? err.message : "Failed to verify the latest SPOT trigger.",
        );
      } finally {
        if (!cancelled) {
          setSpotTriggerChecking(false);
          setSpotTriggerChecked(true);
        }
      }
    };

    void checkSpotTrigger();

    return () => {
      cancelled = true;
    };
  }, [quote]);

  const handleLaunchSpotWorkflow = async () => {
    if (!quote) return;

    setSpotLaunchError(null);
    setSpotLaunching(true);

    try {
      const context = buildSpotResumeContext(quote);
      const triggerResult = await evaluateLatestSpotTrigger(quote);

      if (!triggerResult.is_spot_required || !triggerResult.trigger) {
        router.push(`/quotes/${quote.id}/edit?returnTo=${encodeURIComponent(`/quotes/${quote.id}`)}`);
        return;
      }

      const spe = await createSpotEnvelope({
        shipment_context: {
          origin_country: context.originCountry,
          destination_country: context.destinationCountry,
          origin_code: context.originCode,
          destination_code: context.destinationCode,
          customer_name: context.customerName,
          commodity: context.commodity,
          total_weight_kg: context.chargeableWeight,
          pieces: context.pieces,
          service_scope: context.serviceScope.toLowerCase(),
          payment_term: context.paymentTerm === "COLLECT" ? "collect" : "prepaid",
          missing_components: triggerResult.trigger.missing_components,
        },
        charges: [],
        trigger_code: triggerResult.trigger.code,
        trigger_text: triggerResult.trigger.text,
        conditions: { rate_validity_hours: 72 },
      });

      const params = buildSpotWorkflowParams(quote);
      applySpotTriggerToParams(params, context, triggerResult.trigger);
      params.set("returnTo", `/quotes/${quote.id}`);
      router.push(`/quotes/spot/${spe.id}?${params.toString()}`);
    } catch (err) {
      setSpotLaunchError(err instanceof Error ? err.message : "Failed to open SPOT workflow.");
    } finally {
      setSpotLaunching(false);
    }
  };


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
  const isSpotRequired = Boolean(spotTriggerResult);
  const isArchived = quote.is_archived;
  const canDownloadPDF = (effectiveStatus === "FINALIZED" || effectiveStatus === "SENT");
  const displayTotals = computeResult?.totals ?? quote.latest_version?.totals;
  const displayCurrency = (
    displayTotals?.currency ||
    displayTotals?.total_sell_fcy_currency ||
    quote.latest_version?.totals?.currency ||
    quote.latest_version?.totals?.total_sell_fcy_currency ||
    quote.output_currency ||
    "PGK"
  ).toUpperCase();
  const displayAmountRaw = displayCurrency === "PGK"
    ? (
      displayTotals?.total_quote_amount ||
      displayTotals?.total_sell_pgk_incl_gst ||
      displayTotals?.sell_pgk_incl_gst ||
      displayTotals?.total_sell_pgk ||
      quote.latest_version?.totals?.total_sell_pgk_incl_gst ||
      quote.latest_version?.totals?.sell_pgk_incl_gst ||
      quote.latest_version?.totals?.total_sell_pgk ||
      "0"
    )
    : (
      displayTotals?.total_quote_amount ||
      displayTotals?.total_sell_fcy_incl_gst ||
      displayTotals?.sell_fcy_incl_gst ||
      displayTotals?.total_sell_fcy ||
      quote.latest_version?.totals?.total_sell_fcy_incl_gst ||
      quote.latest_version?.totals?.sell_fcy_incl_gst ||
      quote.latest_version?.totals?.total_sell_fcy ||
      "0"
    );
  const displayAmount = Number(displayAmountRaw || 0);
  const shipmentMetrics = computeShipmentMetrics(quote);
  const fxEntries = buildFxEntries(quote, computeResult);
  const isDomesticQuote = (quote.shipment_type || "").toUpperCase() === "DOMESTIC";
  const resolvedServiceScope = formatServiceScope(quote.service_scope);

  if (spotWorkflowHref) {
    return (
      <div className="container mx-auto max-w-3xl p-6">
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="text-lg">Continuing SPOT Workflow</CardTitle>
            <CardDescription>
              This incomplete quote already has an active SPOT envelope. Redirecting you to the live SPOT workflow now.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-sm text-slate-600">
              <Loader2 className="h-4 w-4 animate-spin" />
              Opening {quote.quote_number} in SPOT mode...
            </div>
            <Button onClick={() => router.replace(spotWorkflowHref)}>
              Open SPOT Now
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

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
              onClick={() => router.push(buildQuoteEditHref(quote))}
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

              {isDomesticQuote ? (
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase">Service Scope</p>
                  <p className="font-medium text-slate-900">{resolvedServiceScope}</p>
                </div>
              ) : (
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
              )}

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
          spotTriggerChecking || !spotTriggerChecked ? (
            <SpotTriggerCheckingCard quote={quote} />
          ) : isSpotRequired ? (
            <SpotWorkflowRequiredCard
              quote={quote}
              spotLaunching={spotLaunching}
              spotLaunchError={spotLaunchError}
              onLaunchSpot={handleLaunchSpotWorkflow}
            />
          ) : (
            <IncompleteQuoteCard
              quote={quote}
              triggerCheckError={spotTriggerCheckError}
              onRetryCheck={async () => {
                if (!quote) {
                  return;
                }
                setSpotTriggerChecking(true);
                setSpotTriggerChecked(false);
                setSpotTriggerCheckError(null);
                try {
                  const result = await evaluateLatestSpotTrigger(quote);
                  setSpotTriggerResult(result.trigger ?? null);
                } catch (err) {
                  setSpotTriggerResult(null);
                  setSpotTriggerCheckError(
                    err instanceof Error ? err.message : "Failed to verify the latest SPOT trigger.",
                  );
                } finally {
                  setSpotTriggerChecking(false);
                  setSpotTriggerChecked(true);
                }
              }}
            />
          )
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
              <p className="text-xs text-slate-500 uppercase font-semibold">Total Quote Amount</p>
              <p className="text-2xl font-bold text-slate-900">
                {displayCurrency} {displayAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
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
                  onClick={() => router.push(buildQuoteEditHref(quote))}
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

function SpotWorkflowRequiredCard({
  quote,
  spotLaunching,
  spotLaunchError,
  onLaunchSpot,
}: {
  quote: V3QuoteComputeResponse;
  spotLaunching: boolean;
  spotLaunchError: string | null;
  onLaunchSpot: () => Promise<void>;
}) {
  const router = useRouter();
  return (
    <Card className="border-amber-200 bg-amber-50/40">
      <CardHeader>
        <CardTitle className="text-lg text-amber-800">SPOT Workflow Required</CardTitle>
        <CardDescription>
          This quote is incomplete and is not linked to an active SPOT envelope yet.
          Launch the current SPOT workflow from here, or return to edit if you need to refresh the quote inputs.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="text-sm text-muted-foreground">Quote: {quote.quote_number}</div>
          {spotLaunchError ? (
            <div className="text-sm text-destructive">{spotLaunchError}</div>
          ) : (
            <div className="text-sm text-muted-foreground">
              The detail view will evaluate the latest SPOT trigger and open the live workflow if it is still required.
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => router.push(`/quotes/${quote.id}/edit`)}>
            Return To Quote Edit
          </Button>
          <Button onClick={() => void onLaunchSpot()} disabled={spotLaunching}>
            {spotLaunching ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Opening SPOT...
              </>
            ) : (
              "Open SPOT Workflow"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SpotTriggerCheckingCard({
  quote,
}: {
  quote: V3QuoteComputeResponse;
}) {
  return (
    <Card className="border-slate-200 bg-slate-50/60">
      <CardHeader>
        <CardTitle className="text-lg text-slate-900">Checking Quote Completion</CardTitle>
        <CardDescription>
          This quote is currently marked incomplete. Verifying the latest SPOT trigger before deciding whether the SPOT workflow is still required.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-3 text-sm text-slate-600">
        <Loader2 className="h-4 w-4 animate-spin" />
        Re-checking {quote.quote_number} against the latest SPOT trigger...
      </CardContent>
    </Card>
  );
}

function IncompleteQuoteCard({
  quote,
  triggerCheckError,
  onRetryCheck,
}: {
  quote: V3QuoteComputeResponse;
  triggerCheckError: string | null;
  onRetryCheck: () => Promise<void>;
}) {
  const router = useRouter();

  return (
    <Card className="border-slate-200 bg-slate-50/60">
      <CardHeader>
        <CardTitle className="text-lg text-slate-900">Incomplete Quote</CardTitle>
        <CardDescription>
          The latest SPOT trigger check does not require the SPOT workflow for this quote. The quote is still incomplete, so return to edit and refresh the missing rate inputs.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="text-sm text-muted-foreground">Quote: {quote.quote_number}</div>
          {triggerCheckError ? (
            <div className="text-sm text-destructive">
              Unable to verify the latest SPOT trigger automatically: {triggerCheckError}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              Return to the quote editor to refresh pricing coverage instead of launching SPOT.
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {triggerCheckError ? (
            <Button variant="outline" onClick={() => void onRetryCheck()}>
              Retry Trigger Check
            </Button>
          ) : null}
          <Button variant="outline" onClick={() => router.push(`/quotes/${quote.id}/edit`)}>
            Return To Quote Edit
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

async function evaluateLatestSpotTrigger(
  quote: V3QuoteComputeResponse,
) {
  const context = buildSpotResumeContext(quote);
  return evaluateSpotTrigger({
    origin_country: context.originCountry,
    destination_country: context.destinationCountry,
    commodity: context.commodity,
    origin_airport: context.originCode,
    destination_airport: context.destinationCode,
    has_valid_buy_rate: true,
    service_scope: context.serviceScope,
    payment_term: context.paymentTerm,
  });
}

function buildQuoteEditHref(quote: V3QuoteComputeResponse): string {
  if (quote.spot_negotiation?.id) {
    const params = buildSpotWorkflowParams(quote);
    params.set("returnTo", `/quotes/${quote.id}`);
    return `/quotes/spot/${quote.spot_negotiation.id}?${params.toString()}`;
  }

  return `/quotes/${quote.id}/edit?returnTo=${encodeURIComponent(`/quotes/${quote.id}`)}`;
}

function buildSpotWorkflowParams(quote: V3QuoteComputeResponse): URLSearchParams {
  const context = buildSpotResumeContext(quote);
  return new URLSearchParams({
    customer_name: context.customerName,
    service_scope: context.serviceScope,
    payment_term: context.paymentTerm,
    output_currency: context.outputCurrency,
    shipment_type: context.shipmentType,
    weight: String(context.chargeableWeight),
    pieces: String(context.pieces),
  });
}

function applySpotTriggerToParams(
  params: URLSearchParams,
  context: SpotResumeContext,
  trigger: TriggerResult,
) {
  params.set("origin_country", context.originCountry);
  params.set("dest_country", context.destinationCountry);
  params.set("origin_code", context.originCode);
  params.set("dest_code", context.destinationCode);
  params.set("commodity", context.commodity);
  params.set("trigger_code", trigger.code);
  params.set("trigger_text", trigger.text);
  if (context.customerId) {
    params.set("customer_id", context.customerId);
  }
  if (trigger.missing_components?.length) {
    params.set("missing_components", trigger.missing_components.join(","));
  } else {
    params.delete("missing_components");
  }
}

type SpotResumeContext = {
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

const SPOT_AIRPORT_COUNTRY_MAP: Record<string, string> = {
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

function buildSpotResumeContext(quote: V3QuoteComputeResponse): SpotResumeContext {
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

function normalizeAirportCode(...candidates: unknown[]): string {
  for (const candidate of candidates) {
    const value = String(candidate || "").trim().toUpperCase();
    if (!value) continue;
    if (/^[A-Z]{3}$/.test(value)) return value;
    const match = value.match(/^([A-Z]{3})\s*-/);
    if (match?.[1]) return match[1];
  }
  return "";
}

function normalizeCountryCode(...candidates: unknown[]): string {
  for (let index = 0; index < candidates.length - 1; index += 1) {
    const value = String(candidates[index] || "").trim().toUpperCase();
    if (/^[A-Z]{2}$/.test(value)) return value;
  }
  const airportCode = String(candidates[candidates.length - 1] || "").trim().toUpperCase();
  return SPOT_AIRPORT_COUNTRY_MAP[airportCode] || "OTHER";
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

  // Derive FX from line-level FCY/PGK totals when explicit rate fields are absent.
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

