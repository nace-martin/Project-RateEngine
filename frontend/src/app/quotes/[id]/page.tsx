"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { createQuoteVersion, getQuoteV3, getQuoteCompute } from "@/lib/api"; // Updated import
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
import RoutingWarning from "@/components/RoutingWarning";
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
import { Loader2 } from "lucide-react";

export default function QuoteDetailPage() {
  const { user, token } = useAuth();
  const params = useParams();
  const id = params.id as string;

  const [quote, setQuote] = useState<V3QuoteComputeResponse | null>(null);
  const [computeResult, setComputeResult] = useState<QuoteComputeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [manualOverrides, setManualOverrides] = useState<V3ManualOverride[]>([]);
  const [recalculateError, setRecalculateError] = useState<string | null>(null);
  const [recalculateLoading, setRecalculateLoading] = useState(false);
  const [recalculateSuccess, setRecalculateSuccess] = useState(false);

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
    if (manualOverrides.length === 0) {
      setRecalculateError("Add at least one manual rate before recalculating.");
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
      <div className="container mx-auto max-w-4xl p-4">
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!quote) {
    return (
      <div className="container mx-auto max-w-4xl p-4">
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

  return (
    <div className="container mx-auto max-w-4xl space-y-6 p-4">
      <CustomerSummaryCard quote={quote} />

      {/* Display routing warning if VIA routing is required */}
      {computeResult?.routing && (
        <RoutingWarning routingInfo={computeResult.routing} />
      )}

      {isIncomplete ? (
        <ManualSourcingView
          quote={quote}
          manualOverrides={manualOverrides}
          recalculateError={recalculateError}
          recalculateLoading={recalculateLoading}
          recalculateSuccess={recalculateSuccess}
          onManualOverrideSubmit={handleManualOverrideSubmit}
          onRecalculate={handleRecalculate}
        />
      ) : (
        computeResult ? (
          <QuoteFinancialBreakdown result={computeResult} />
        ) : (
          <QuoteResultDisplay quote={quote} />
        )
      )}
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

  return (
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
              disabled={recalculateLoading || manualOverrides.length === 0}
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
  );
}

function CustomerSummaryCard({ quote }: { quote: V3QuoteComputeResponse }) {
  const customerDetails =
    quote.customer && typeof quote.customer === "object"
      ? quote.customer
      : null;
  const contactDetails =
    quote.contact && typeof quote.contact === "object"
      ? quote.contact
      : null;

  const customerName =
    customerDetails?.name ||
    customerDetails?.company_name ||
    (typeof quote.customer === "string" ? quote.customer : "Customer");
  const customerEmail = customerDetails?.email || null;

  const contactName = contactDetails
    ? [contactDetails.first_name, contactDetails.last_name]
      .filter(Boolean)
      .join(" ")
      .trim() || contactDetails.email || "Contact"
    : typeof quote.contact === "string"
      ? quote.contact
      : "Contact";
  const contactEmail = contactDetails?.email || null;

  // Helper to clean location names (remove airport codes and airport names)
  const cleanLocationName = (location: string) => {
    // Remove airport codes like "BNE - " or "POM - "
    let cleaned = location.replace(/^[A-Z]{3}\s*-\s*/i, '');
    // Remove common airport name suffixes and patterns
    cleaned = cleaned.replace(/\s+(Intl|International|Airport)(\s|$)/gi, '');
    // Remove specific airport names (Jacksons, etc.)
    cleaned = cleaned.replace(/\s+(Jacksons|Jackson)(\s|$)/gi, '');
    return cleaned.trim();
  };

  // Expand service scope abbreviation
  const expandServiceScope = (scope: string) => {
    const expansions: Record<string, string> = {
      'D2D': 'Door to Door',
      'CY': 'Container Yard',
      'CFS': 'Container Freight Station',
    };
    return expansions[scope] || scope;
  };

  return (
    <div className="space-y-6">
      {/* Professional Header */}
      <div className="bg-slate-900 text-white rounded-lg p-8 shadow-sm">
        <div className="flex items-start justify-between gap-8">
          <div className="flex-1">
            <div className="flex items-center gap-4 mb-3">
              <h1 className="text-3xl font-semibold tracking-tight">
                {quote.quote_number}
              </h1>
              <Badge
                variant={quote.status === 'DRAFT' ? 'secondary' : quote.status === 'ACCEPTED' ? 'default' : 'outline'}
                className="bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700"
              >
                {quote.status}
              </Badge>
            </div>
            <div className="flex items-center gap-6 text-sm text-slate-400">
              <span>
                Created {new Date(quote.created_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric'
                })}
              </span>
              <span className="text-slate-600">•</span>
              <span className="uppercase text-xs font-medium tracking-wider">
                {quote.shipment_type}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Clean Info Grid */}
      <Card className="overflow-hidden border-slate-200">
        <CardContent className="p-0">
          <div className="divide-y divide-slate-100">
            {/* Customer & Contact Row */}
            <div className="grid grid-cols-2 divide-x divide-slate-100">
              <div className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Customer
                </div>
                <div>
                  <div className="font-semibold text-slate-900 mb-1">
                    {customerName}
                  </div>
                  {customerEmail && (
                    <div className="text-sm text-slate-600">
                      {customerEmail}
                    </div>
                  )}
                </div>
              </div>
              <div className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Contact
                </div>
                <div>
                  <div className="font-semibold text-slate-900 mb-1">
                    {contactName}
                  </div>
                  {contactEmail && (
                    <div className="text-sm text-slate-600">
                      {contactEmail}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Route & Service Scope Row */}
            <div className="grid grid-cols-2 divide-x divide-slate-100">
              <div className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Route
                </div>
                <div>
                  <div className="font-semibold text-slate-900 mb-1 flex items-center gap-2">
                    <span>{cleanLocationName(quote.origin_location)}</span>
                    <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                    <span>{cleanLocationName(quote.destination_location)}</span>
                  </div>
                  <div className="text-sm text-slate-600">
                    {expandServiceScope(quote.service_scope)}
                  </div>
                </div>
              </div>
              <div className="p-6">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">
                  Service Details
                </div>
                <div className="flex items-center gap-6 text-sm">
                  <div>
                    <span className="text-slate-500">Mode: </span>
                    <span className="text-slate-900 font-medium">{quote.mode}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Incoterm: </span>
                    <span className="text-slate-700 font-mono text-xs bg-slate-100 px-2 py-0.5 rounded">{quote.incoterm}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Payment: </span>
                    <span className="text-slate-700 font-mono text-xs bg-slate-100 px-2 py-0.5 rounded">{quote.payment_term}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
