"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { createQuoteVersion, getQuoteV3 } from "@/lib/api"; // Updated import
import {
  QuoteVersionCreatePayload,
  V3ManualOverride,
  V3QuoteComputeResponse,
  V3QuoteLine,
} from "@/lib/types"; // Updated import
import ManualRateForm from "@/components/ManualRateForm";
import QuoteResultDisplay from "@/components/QuoteResultDisplay";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2 } from "lucide-react";

export default function QuoteDetailPage() {
  const { user, token } = useAuth();
  const params = useParams();
  const id = params.id as string;

  const [quote, setQuote] = useState<V3QuoteComputeResponse | null>(null);
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
        <QuoteResultDisplay quote={quote} />
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
    <Card>
        <CardHeader>
          <CardTitle className="text-3xl">
            Incomplete Quote - Awaiting Manual Rates
          </CardTitle>
          <CardDescription>
            Quote {quote.quote_number} requires manual rates before it can be
            finalized.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="mb-6 text-muted-foreground">
            Review each charge line below. Any line that is missing a rate must
            be updated before this quote can be finalized and sent to the
            customer.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Charge Line</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Manual Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mergedLines.map((line) => {
                const override = line.manual_override;
                const isMissing = !override && line.is_rate_missing;
                const rowClass = isMissing
                  ? "bg-red-50/70"
                  : override
                  ? "bg-amber-50/70"
                  : undefined;
                return (
                  <TableRow key={line.id} className={rowClass}>
                    <TableCell>
                      <div className="font-semibold">
                        {line.service_component.description}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {line.service_component.category}
                      </p>
                    </TableCell>
                    <TableCell
                      className={
                        override
                          ? "text-amber-700 font-semibold"
                          : isMissing
                          ? "text-red-600 font-semibold"
                          : "text-muted-foreground"
                      }
                    >
                      {override
                        ? `Manual rate captured (${override.cost_fcy} ${override.currency})`
                        : isMissing
                        ? "Manual rate required"
                        : "Rate ready"}
                    </TableCell>
                    <TableCell className="text-right">
                      {override ? (
                        <div className="space-y-1 text-left sm:text-right">
                          <div className="font-semibold">
                            {override.cost_fcy} {override.currency}
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {override.unit}
                            {override.min_charge_fcy
                              ? ` • Min ${override.min_charge_fcy}`
                              : ""}
                          </p>
                          <ManualRateForm
                            service_component_id={line.service_component.id}
                            service_component_desc={
                              line.service_component.description
                            }
                            onSubmit={onManualOverrideSubmit}
                            triggerLabel="Update Rate"
                          />
                        </div>
                      ) : isMissing ? (
                        <ManualRateForm
                          service_component_id={line.service_component.id}
                          service_component_desc={
                            line.service_component.description
                          }
                          onSubmit={onManualOverrideSubmit}
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
        <CardContent className="space-y-4">
          <div>
            <h3 className="text-xl font-semibold">Manual Rates Entered</h3>
            {manualOverrides.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No manual rates captured yet.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Charge Line</TableHead>
                    <TableHead className="text-right">Cost (FCY)</TableHead>
                    <TableHead>Currency</TableHead>
                    <TableHead>Unit</TableHead>
                    <TableHead className="text-right">Min Charge</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {manualOverrides.map((override) => (
                    <TableRow
                      key={override.service_component_id}
                      className="bg-muted/30"
                    >
                      <TableCell>
                        {lineLookup[override.service_component_id] ||
                          override.service_component_id}
                      </TableCell>
                      <TableCell className="text-right">
                        {override.cost_fcy}
                      </TableCell>
                      <TableCell>{override.currency}</TableCell>
                      <TableCell>{override.unit}</TableCell>
                      <TableCell className="text-right">
                        {override.min_charge_fcy ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
          {recalculateError && (
            <Alert variant="destructive">
              <AlertTitle>Unable to Recalculate</AlertTitle>
              <AlertDescription>{recalculateError}</AlertDescription>
            </Alert>
          )}
          {recalculateSuccess && (
            <Alert variant="default">
              <AlertTitle>Quote Finalized</AlertTitle>
              <AlertDescription>
                Manual rates saved and recalculation completed successfully.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
        <CardFooter className="flex justify-end">
          <Button
            disabled={recalculateLoading || manualOverrides.length === 0}
            onClick={onRecalculate}
          >
            {recalculateLoading && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Recalculate & Finalize
          </Button>
        </CardFooter>
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">Customer Details</CardTitle>
        <CardDescription>Quote {quote.quote_number}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-sm text-muted-foreground">Customer</p>
            <p className="text-lg font-semibold">{customerName}</p>
            {customerEmail && (
              <p className="text-sm text-muted-foreground">{customerEmail}</p>
            )}
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Primary Contact</p>
            <p className="text-lg font-semibold">{contactName}</p>
            {contactEmail && (
              <p className="text-sm text-muted-foreground">{contactEmail}</p>
            )}
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Route</p>
            <p className="text-lg font-semibold">
              {quote.origin_location} → {quote.destination_location}
            </p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Mode / Scope</p>
            <p className="text-lg font-semibold">
              {quote.mode} · {quote.service_scope}
            </p>
            <p className="text-sm text-muted-foreground">
              Incoterm {quote.incoterm}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
