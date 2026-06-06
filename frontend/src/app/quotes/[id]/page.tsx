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
import InternalInspectionAlert from "@/components/quotes/InternalInspectionAlert";
import QuoteDetailFooter from "@/components/quotes/QuoteDetailFooter";
import {
  SpotWorkflowRequiredCard,
  SpotTriggerCheckingCard,
  IncompleteQuoteCard,
} from "@/components/quotes/SpotTriggerCards";

import RoutingWarning from "@/components/RoutingWarning";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, ArrowLeft, CheckCircle2 } from "lucide-react";
import { QuoteStatusBadge, QuoteStatusActions } from "@/components/QuoteStatusBadge";
import { formatServiceScope } from "@/lib/display";
import { getEffectiveQuoteStatus } from "@/lib/quote-helpers";
import type { TriggerResult } from "@/lib/spot-types";
import {
  computeShipmentMetrics,
  buildSpotResumeContext,
  buildFxEntries,
  type SpotResumeContext,
} from "@/lib/quote-detail-helpers";
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

  const handleDownloadPDF = async () => {
    if (!quote) return;
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
  };

  const handleRetrySpotTriggerCheck = async () => {
    if (!quote) return;
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
  };

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
        <InternalInspectionAlert
          quote={quote}
          isDomesticQuote={isDomesticQuote}
          resolvedServiceScope={resolvedServiceScope}
          fxEntries={fxEntries}
          shipmentMetrics={shipmentMetrics}
        />

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
              onReturnToEdit={() => router.push(`/quotes/${quote.id}/edit`)}
            />
          ) : (
            <IncompleteQuoteCard
              quote={quote}
              triggerCheckError={spotTriggerCheckError}
              onRetryCheck={handleRetrySpotTriggerCheck}
              onReturnToEdit={() => router.push(`/quotes/${quote.id}/edit`)}
            />
          )
        ) : (
          /* Full-width Layout for Finalized Quotes */
          <div className="space-y-6">
            <QuoteFinancialBreakdown result={quote} />
          </div>
        )}
      </div>

      {/* Sticky Footer Action Bar */}
      <QuoteDetailFooter
        quote={quote}
        effectiveStatus={effectiveStatus}
        displayCurrency={displayCurrency}
        displayAmount={displayAmount}
        canDownloadPDF={canDownloadPDF}
        pdfDownloading={pdfDownloading}
        onDownloadPDF={handleDownloadPDF}
        onEditQuote={() => router.push(buildQuoteEditHref(quote))}
        onStatusChange={() => {
          getQuoteV3(id).then((data) => setQuote(data));
        }}
      />

    </div >
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



