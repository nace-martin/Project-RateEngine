"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { createQuoteVersion, getQuoteV3, getQuoteCompute, downloadQuotePDF } from "@/lib/api";
import {
  QuoteVersionCreatePayload,
  V3ManualOverride,
  V3QuoteComputeResponse,
  V3QuoteLine,
  QuoteComputeResult,
} from "@/lib/types";
import ManualRateForm from "@/components/ManualRateForm";
import QuoteResultDisplay from "@/components/QuoteResultDisplay";
import QuoteFinancialBreakdown from "@/components/QuoteFinancialBreakdown";
import QuoteSummaryBar from "@/components/QuoteSummaryBar";
import QuoteSettings from "@/components/QuoteSettings";
import RoutingWarning from "@/components/RoutingWarning";
import { BucketSourcingView } from "@/components/pricing/BucketSourcingView";
import { SpotChargeResultDisplay } from "@/components/pricing/SpotChargeResultDisplay";
import { getSpotChargesForQuote } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Loader2, ChevronRight, ArrowLeft, CheckCircle } from "lucide-react";
import { QuoteStatusBadge, QuoteStatusActions, isQuoteEditable } from "@/components/QuoteStatusBadge";

export default function QuoteDetailPage() {
  const { user, token } = useAuth();
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [quote, setQuote] = useState<V3QuoteComputeResponse | null>(null);
  const [computeResult, setComputeResult] = useState<QuoteComputeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manualOverrides, setManualOverrides] = useState<V3ManualOverride[]>([]);
  const [recalculateError, setRecalculateError] = useState<string | null>(null);
  const [recalculateLoading, setRecalculateLoading] = useState(false);
  const [recalculateSuccess, setRecalculateSuccess] = useState(false);
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

  useEffect(() => {
    if (quote?.latest_version?.payload_json?.overrides) {
      setManualOverrides(quote.latest_version.payload_json.overrides);
    } else {
      setManualOverrides([]);
    }
  }, [quote]);

  const handleManualOverrideSubmit = (override: V3ManualOverride) => {
    setRecalculateSuccess(false);
    setRecalculateError(null);
    setManualOverrides((prev) => {
      const index = prev.findIndex(
        (item) => item.service_component_id === override.service_component_id,
      );
      if (index >= 0) {
        const updated = [...prev];
        updated[index] = override;
        return updated;
      }
      return [...prev, override];
    });
  };

  const handleRecalculate = async () => {
    if (!quote) {
      setRecalculateError("Quote data is unavailable.");
      return;
    }

    // Only require manual overrides if there are actually missing rates
    const hasMissing = quote.latest_version.lines.some(l => l.is_rate_missing);
    if (hasMissing && manualOverrides.length === 0) {
      setRecalculateError("Add manual rates for missing charges before recalculating.");
      return;
    }
    const payload: QuoteVersionCreatePayload = {
      charges: manualOverrides.map((override) => {
        const normalized: V3ManualOverride = {
          service_component_id: override.service_component_id,
          cost_fcy: override.cost_fcy,
          currency: override.currency.toUpperCase(),
          unit: override.unit,
        };
        if (override.min_charge_fcy) {
          normalized.min_charge_fcy = override.min_charge_fcy;
        }
        if (override.valid_until) {
          normalized.valid_until = override.valid_until;
        }
        return normalized;
      }),
    };
    setRecalculateLoading(true);
    setRecalculateError(null);
    setRecalculateSuccess(false);
    try {
      const updatedQuote = await createQuoteVersion(token, quote.id, payload);
      setQuote(updatedQuote);
      setManualOverrides(
        updatedQuote.latest_version?.payload_json?.overrides ??
        payload.charges,
      );
      setRecalculateSuccess(true);

      // Refresh compute result
      const computeData = await getQuoteCompute(quote.id);
      setComputeResult(computeData);

    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to finalize quote.";
      setRecalculateError(message);
    } finally {
      setRecalculateLoading(false);
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

  const isIncomplete = quote.status === "INCOMPLETE";

  // For finalized view, use the new two-column layout
  const showFinalizedLayout = !isIncomplete;
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
              const speId = quote.latest_version?.payload_json?.spot_envelope_id;
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
                {quote.latest_version?.totals?.currency || 'PGK'} {quote.latest_version?.totals?.total_sell_incl_gst?.toLocaleString()}
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

interface ManualSourcingViewProps {
  quote: V3QuoteComputeResponse;
  manualOverrides: V3ManualOverride[];
  recalculateLoading: boolean;
  recalculateError: string | null;
  recalculateSuccess: boolean;
  onManualOverrideSubmit: (override: V3ManualOverride) => void;
  onRecalculate: () => void;
}

type QuoteLineWithOverride = V3QuoteLine & {
  manual_override?: V3ManualOverride;
};

function ManualSourcingView({
  quote,
  manualOverrides,
  recalculateLoading,
  recalculateError,
  recalculateSuccess,
  onManualOverrideSubmit,
  onRecalculate,
}: ManualSourcingViewProps) {
  const lines = quote.latest_version.lines;
  const lineLookup = useMemo(() => {
    return lines.reduce<Record<string, string>>((acc, line) => {
      acc[line.service_component.id] = line.service_component.description;
      return acc;
    }, {});
  }, [lines]);
  const mergedLines = useMemo<QuoteLineWithOverride[]>(() => {
    const overrideMap = manualOverrides.reduce<Map<string, V3ManualOverride>>(
      (acc, override) => acc.set(override.service_component_id, override),
      new Map(),
    );
    return lines.map((line) => {
      const override = overrideMap.get(line.service_component.id);
      if (!override) {
        return line;
      }
      return {
        ...line,
        is_rate_missing: false,
        service_component: {
          ...line.service_component,
          description: `${line.service_component.description} (Manual Rate Added)`,
        },
        manual_override: override,
      };
    });
  }, [lines, manualOverrides]);

  // Check if any lines still have missing rates (not covered by manual overrides)
  const hasMissingRates = useMemo(() => {
    return mergedLines.some((line) => !line.manual_override && line.is_rate_missing);
  }, [mergedLines]);

  return (
    <div className="pb-32"> {/* Added padding for sticky footer in manual mode too */}
      <Card className="overflow-hidden border-destructive/20 shadow-md">
        <CardHeader className="bg-destructive/5 pb-4 border-b border-destructive/10">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-destructive/10 rounded-full">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-destructive"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" x2="12" y1="9" y2="13" /><line x1="12" x2="12.01" y1="17" y2="17" /></svg>
            </div>
            <div>
              <CardTitle className="text-xl text-destructive">
                Action Required: Manual Rates
              </CardTitle>
              <CardDescription>
                Some charges require manual pricing before this quote can be finalized.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader className="bg-muted/50">
              <TableRow>
                <TableHead className="pl-6">Charge Line</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right pr-6">Manual Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mergedLines.map((line) => {
                const override = line.manual_override;
                const isMissing = !override && line.is_rate_missing;
                const rowClass = isMissing
                  ? "bg-destructive/5 hover:bg-destructive/10"
                  : override
                    ? "bg-amber-50/50 hover:bg-amber-50"
                    : "hover:bg-muted/30";
                return (
                  <TableRow key={line.id} className={rowClass}>
                    <TableCell className="pl-6">
                      <div className="font-semibold text-foreground">
                        {line.service_component.description}
                      </div>
                      <p className="text-xs text-muted-foreground uppercase tracking-wider mt-0.5">
                        {line.service_component.category}
                      </p>
                    </TableCell>
                    <TableCell>
                      {override ? (
                        <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-200">
                          Manual Rate
                        </Badge>
                      ) : isMissing ? (
                        <Badge variant="destructive">
                          Required
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">
                          Ready
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right pr-6">
                      {override ? (
                        <div className="flex items-center justify-end gap-3">
                          <div className="text-right">
                            <div className="font-mono font-semibold">
                              {override.cost_fcy} {override.currency}
                            </div>
                            <p className="text-xs text-muted-foreground">
                              {override.unit}
                              {override.min_charge_fcy
                                ? ` • Min ${override.min_charge_fcy}`
                                : ""}
                            </p>
                          </div>
                          <ManualRateForm
                            service_component_id={line.service_component.id}
                            service_component_desc={
                              line.service_component.description
                            }
                            onSubmit={onManualOverrideSubmit}
                            triggerLabel="Edit"
                          />
                        </div>
                      ) : isMissing ? (
                        <ManualRateForm
                          service_component_id={line.service_component.id}
                          service_component_desc={
                            line.service_component.description
                          }
                          onSubmit={onManualOverrideSubmit}
                          triggerLabel="Add Rate"
                        />
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
        <CardContent className="p-6 bg-muted/10 border-t">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">Manual Rates Summary</h3>
              {manualOverrides.length === 0 ? (
                <p className="text-sm text-muted-foreground italic">
                  No manual rates captured yet.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {manualOverrides.map((override) => (
                    <Badge key={override.service_component_id} variant="outline" className="bg-background">
                      {lineLookup[override.service_component_id] || override.service_component_id}: {override.cost_fcy} {override.currency}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              {recalculateError && (
                <p className="text-sm text-destructive font-medium">{recalculateError}</p>
              )}
              {recalculateSuccess && (
                <p className="text-sm text-emerald-600 font-medium">Quote updated successfully!</p>
              )}
              <Button
                size="lg"
                disabled={recalculateLoading || (hasMissingRates && manualOverrides.length === 0)}
                onClick={onRecalculate}
                className="shadow-md"
              >
                {recalculateLoading && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Recalculate & Finalize
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
