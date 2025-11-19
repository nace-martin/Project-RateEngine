"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Loader2, PlusCircle, ArrowRight } from "lucide-react";
import ProtectedRoute from "@/components/protected-route";
import { useAuth } from "@/context/auth-context";
import { getQuotesV3 } from "@/lib/api";
import type { V3QuoteComputeResponse } from "@/lib/types";
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
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

const formatCurrency = (value: number, currency = "PGK") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value || 0);

export default function HomePage() {
  const { user } = useAuth();
  const [recentQuotes, setRecentQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) {
      return;
    }
    const fetchQuotes = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getQuotesV3();
        setRecentQuotes(data.slice(0, 5));
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Unable to load recent quotes.";
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    fetchQuotes();
  }, [user]);

  const metrics = useMemo(() => {
    const readyQuotes = recentQuotes.filter(
      (quote) => !quote.latest_version.totals.has_missing_rates,
    );
    const currency =
      recentQuotes[0]?.latest_version.totals.total_sell_fcy_currency ?? "PGK";
    const pipelineValue = recentQuotes.reduce((sum, quote) => {
      const amount = parseFloat(
        quote.latest_version.totals.total_sell_fcy_incl_gst || "0",
      );
      return sum + (isNaN(amount) ? 0 : amount);
    }, 0);

    return {
      readyCount: readyQuotes.length,
      totalQuotes: recentQuotes.length,
      pipelineValue,
      currency,
    };
  }, [recentQuotes]);

  const renderRecentQuotes = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-10 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading your latest quotes...
        </div>
      );
    }

    if (error) {
      return (
        <Alert variant="destructive">
          <AlertTitle>Something went wrong</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      );
    }

    if (recentQuotes.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center gap-3 py-8 text-center text-muted-foreground">
          <p>No quotes yet. Kick things off with your first one.</p>
          <Button variant="secondary" asChild>
            <Link href="/quotes/new">
              <PlusCircle className="mr-2 h-4 w-4" />
              Create a Quote
            </Link>
          </Button>
        </div>
      );
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Quote #</TableHead>
            <TableHead>Route</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Total (inc. GST)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {recentQuotes.map((quote) => (
            <TableRow key={quote.id}>
              <TableCell>
                <Button variant="link" asChild>
                  <Link href={`/quotes/${quote.id}`}>{quote.quote_number}</Link>
                </Button>
              </TableCell>
              <TableCell>
                {quote.origin_location}
                {" -> "}
                {quote.destination_location}
              </TableCell>
              <TableCell>
                <Badge
                  variant={
                    quote.latest_version.totals.has_missing_rates
                      ? "destructive"
                      : "secondary"
                  }
                >
                  {quote.status}
                </Badge>
              </TableCell>
              <TableCell className="text-right font-medium">
                {formatCurrency(
                  parseFloat(
                    quote.latest_version.totals.total_sell_fcy_incl_gst || "0",
                  ),
                  quote.latest_version.totals.total_sell_fcy_currency,
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  };

  const displayName = user?.username;
  const greeting = displayName ? `Welcome back, ${displayName}` : "Welcome to RateEngine";

  return (
    <ProtectedRoute>
      <main className="container mx-auto space-y-8 py-8">
        <section className="rounded-2xl border bg-white px-6 py-8 shadow-sm">
          <p className="text-sm font-semibold uppercase tracking-wide text-primary">
            {greeting}
          </p>
          <h1 className="mt-2 text-4xl font-bold text-foreground">
            Your quoting control center
          </h1>
          <p className="mt-3 max-w-2xl text-lg text-muted-foreground">
            Monitor the pipeline, draft new quotes, and keep customers moving —
            all from one place.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button variant="secondary" asChild>
              <Link href="/quotes/new">
                <PlusCircle className="mr-2 h-4 w-4" />
                New Quote
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/quotes">
                View Quotes
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
            <Button variant="ghost" asChild>
              <Link href="/customers">Manage Customers</Link>
            </Button>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Quotes in progress</CardTitle>
              <CardDescription>Drafts and recently sent quotes.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-semibold">{metrics.totalQuotes}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Ready to send</CardTitle>
              <CardDescription>No missing rates detected.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-semibold">{metrics.readyCount}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Pipeline value</CardTitle>
              <CardDescription>Includes GST where applicable.</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-4xl font-semibold">
                {formatCurrency(metrics.pipelineValue, metrics.currency)}
              </p>
            </CardContent>
          </Card>
        </section>

        <Card>
          <CardHeader>
            <CardTitle>Recent activity</CardTitle>
            <CardDescription>Latest quotes you and the team touched.</CardDescription>
          </CardHeader>
          <CardContent>{renderRecentQuotes()}</CardContent>
        </Card>
      </main>
    </ProtectedRoute>
  );
}
