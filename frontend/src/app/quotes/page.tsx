"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/auth-context";
import { getQuotesV3 } from "@/lib/api"; // Updated import
import { V3QuoteComputeResponse } from "@/lib/types"; // Updated import
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

export default function QuotesPage() {
  const { user } = useAuth();
  const [quotes, setQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      const fetchQuotes = async () => {
        setLoading(true);
        setError(null);
        try {
          // Use the new V3 API function
          const data = await getQuotesV3();
          setQuotes(data.results);
        } catch (err: unknown) {
          const message =
            err instanceof Error ? err.message : "An unexpected error occurred.";
          setError(message);
        } finally {
          setLoading(false);
        }
      };
      fetchQuotes();
    }
  }, [user]);

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
            You haven&apos;t created any quotes yet.
          </p>
          <Button variant="secondary" asChild>
            <Link href="/quotes/new">
              <PlusCircle className="mr-2 h-4 w-4" />
              Create New Quote
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
            <TableHead>From</TableHead>
            <TableHead>To</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Total (Inc. GST)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {quotes.map((quote) => (
            <TableRow key={quote.id}>
              <TableCell>
                <Button variant="link" asChild>
                  <Link href={`/quotes/${quote.id}`}>{quote.quote_number}</Link>
                </Button>
              </TableCell>
              <TableCell>{quote.origin_location}</TableCell>
              <TableCell>{quote.destination_location}</TableCell>
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
        <h1 className="text-3xl font-bold">Quotes Dashboard</h1>
        <Button variant="secondary" asChild>
          <Link href="/quotes/new">
            <PlusCircle className="mr-2 h-4 w-4" />
            New Quote
          </Link>
        </Button>
      </div>

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
