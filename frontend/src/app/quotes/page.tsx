"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import { getQuotesV3, listSpotEnvelopes } from "@/lib/api";
import { V3QuoteComputeResponse } from "@/lib/types";
import { SpotPricingEnvelope } from "@/lib/spot-types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, PlusCircle } from "lucide-react";
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";

// Helper to format currency
const formatCurrency = (amountStr: string, currency: string) => {
  const amount = parseFloat(amountStr || "0");
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
  }).format(amount);
};

// Helper to format route as "City (CODE)"
const formatRoute = (location: string): string => {
  if (!location) return '';
  const match = location.match(/^([A-Z]{3})\s*-\s*(.+)$/);
  if (match) {
    const [, code, fullName] = match;
    const cityName = fullName.replace(/\s+(Airport|Intl|International|Jacksons|Terminal|Apt).*$/i, '').trim();
    return `${cityName} (${code})`;
  }
  return location;
};

// Helper to format date
const formatDate = (dateStr: string): string => {
  try {
    return new Date(dateStr).toLocaleDateString('en-AU', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
};

export default function QuotesPage() {
  const { user } = useAuth();
  const { canEditQuotes, isFinance } = usePermissions();
  const [quotes, setQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [spotDrafts, setSpotDrafts] = useState<SpotPricingEnvelope[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      const fetchData = async () => {
        setLoading(true);
        setError(null);
        try {
          // Fetch both quotes and SPOT drafts in parallel
          const [quotesData, draftsData] = await Promise.all([
            getQuotesV3(),
            listSpotEnvelopes('draft').catch(() => []), // Silently fail if no drafts
          ]);
          setQuotes(quotesData.results);
          setSpotDrafts(draftsData);
        } catch (err: unknown) {
          const message =
            err instanceof Error ? err.message : "An unexpected error occurred.";
          setError(message);
        } finally {
          setLoading(false);
        }
      };
      fetchData();
    }
  }, [user]);

  const renderSpotDrafts = () => {
    if (spotDrafts.length === 0) return null;

    return (
      <Card className="mb-6 border-amber-200 bg-amber-50/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-amber-800">In-Progress SPOT Quotes</CardTitle>
          <CardDescription className="text-amber-700">
            These quotes are saved as drafts. Click &quot;Resume&quot; to continue.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {spotDrafts.map((draft) => {
              const ctx = draft.shipment;
              if (!ctx) return null; // Skip if no shipment context
              return (
                <div
                  key={draft.id}
                  className="flex items-center justify-between rounded-lg border border-amber-200 bg-white p-3"
                >
                  <div className="flex items-center gap-6">
                    <div>
                      <span className="font-medium text-slate-900">
                        {ctx.origin_code} → {ctx.destination_code}
                      </span>
                      <span className="ml-2 text-sm text-slate-500">
                        ({ctx.commodity || 'GCR'})
                      </span>
                    </div>
                    <div className="text-sm text-slate-600">
                      {ctx.total_weight_kg?.toFixed(0) || '0'} kg
                      {ctx.pieces && ctx.pieces > 1 ? ` × ${ctx.pieces} pcs` : ''}
                    </div>
                    <div className="text-sm text-slate-400">
                      Saved {formatDate(draft.created_at)}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-amber-400 text-amber-700 hover:bg-amber-100"
                    onClick={() => window.location.href = `/quotes/spot/${draft.id}`}
                  >
                    Resume
                  </Button>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    );
  };

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center p-8">
          <Loader2 className="mr-2 h-8 w-8 animate-spin" />
          <span>Loading quotes...</span>
        </div>
      );
    }

    if (error) {
      return (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      );
    }

    if (quotes.length === 0) {
      return (
        <div className="text-center">
          <p className="mb-4 text-lg text-muted-foreground">
            {isFinance ? "No quotes available for review." : "You haven't created any quotes yet."}
          </p>
          {canEditQuotes && (
            <Button variant="secondary" asChild>
              <Link href="/quotes/new">
                <PlusCircle className="mr-2 h-4 w-4" />
                Create New Quote
              </Link>
            </Button>
          )}
        </div>
      );
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Quote #</TableHead>
            <TableHead>From</TableHead>
            <TableHead>To</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Total (Inc. GST)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {quotes.map((quote) => (
            <TableRow
              key={quote.id}
              className="cursor-pointer hover:bg-muted/50"
              onClick={() => window.location.href = `/quotes/${quote.id}`}
            >
              <TableCell>
                <span className="text-primary font-medium">
                  {quote.quote_number}
                </span>
              </TableCell>
              <TableCell>{formatRoute(quote.origin_location)}</TableCell>
              <TableCell>{formatRoute(quote.destination_location)}</TableCell>
              <TableCell>
                <QuoteStatusBadge status={quote.status} />
              </TableCell>
              <TableCell className="text-right font-medium">
                {formatCurrency(
                  quote.latest_version.totals.total_sell_fcy_incl_gst,
                  quote.latest_version.totals.total_sell_fcy_currency,
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  return (
    <div className="container mx-auto p-4">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold">
          {isFinance ? "Quotes Register" : "Quotes Dashboard"}
        </h1>
        {canEditQuotes && (
          <Button variant="secondary" asChild>
            <Link href="/quotes/new">
              New Quote
            </Link>
          </Button>
        )}
      </div>

      {/* SPOT Drafts Section */}
      {renderSpotDrafts()}

      <Card>
        <CardHeader>
          <CardTitle>Recent Quotes</CardTitle>
          <CardDescription>
            Here is a list of your most recent quotes.
          </CardDescription>
        </CardHeader>
        <CardContent>{renderContent()}</CardContent>
      </Card>
    </div>
  );
}
