"use client"; // Needs to be a client component for hooks and data fetching

import { useState, useEffect } from "react";
import { useParams } from "next/navigation"; // To get the [id] from the URL
import Link from "next/link";
import { Loader2, AlertCircle } from "lucide-react";

// Import API client and types
import { apiClient } from "@/lib/api";
import type { V3QuoteComputeResponse } from "@/lib/types"; // Reuse the compute response type

// Import Shadcn UI Components
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
import { Separator } from "@/components/ui/separator";

// Helper function to format currency (consider moving to a utils file)
const formatCurrency = (amount: string | number | null | undefined, currency: string) => {
  if (amount === null || amount === undefined) return "-";
  const numericAmount = typeof amount === 'string' ? parseFloat(amount) : amount;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numericAmount);
};

// Helper function to format dates (consider moving to a utils file)
const formatDate = (dateString: string | undefined) => {
  if (!dateString) return "-";
  try {
    return new Date(dateString).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateString; // Return original if parsing fails
  }
}

export default function QuoteDisplayPage() {
  const params = useParams();
  const quoteId = params.id as string; // Get the UUID from the URL

  const [quoteData, setQuoteData] = useState<V3QuoteComputeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!quoteId) return; // Don't fetch if ID is missing

    const fetchQuote = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await apiClient.get<V3QuoteComputeResponse>(`/api/v3/quotes/${quoteId}/`);
        setQuoteData(response.data);
      } catch (err: unknown) {
        console.error("Error fetching quote:", err);
        const message =
          err instanceof Error && err.message
            ? err.message
            : "Failed to load quote details.";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    };

    fetchQuote();
  }, [quoteId]); // Refetch if the quoteId changes

  // --- Render Loading State ---
  if (isLoading) {
    return (
      <div className="container mx-auto flex h-60 items-center justify-center p-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="ml-2">Loading quote details...</span>
      </div>
    );
  }

  // --- Render Error State ---
  if (error) {
    return (
      <div className="container mx-auto max-w-2xl p-4">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button variant="link" asChild className="mt-4">
           <Link href="/quotes">Back to Quotes List</Link>
        </Button>
      </div>
    );
  }

  // --- Render Quote Details ---
  if (!quoteData) {
    // Should ideally not happen if loading/error states are correct
    return <div className="container mx-auto p-4">Quote data not found.</div>;
  }

  const version = quoteData.latest_version; // Use the latest version

  return (
    <div className="container mx-auto max-w-5xl p-4 space-y-6">
      {/* --- Header --- */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Quote: {quoteData.quote_number}</h1>
        <Badge variant={version.totals.has_missing_rates ? "destructive" : "secondary"}>
          {quoteData.status} {version.totals.has_missing_rates ? "(Incomplete)" : ""}
        </Badge>
        {/* TODO: Add PDF Download Button here later */}
      </div>
      <p className="text-muted-foreground">Version {version.version_number} - Created: {formatDate(version.created_at)}</p>

      {/* --- Main Details Card --- */}
      <Card>
        <CardHeader>
          <CardTitle>Shipment Summary</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Customer ID</p>
            <p>{quoteData.customer}</p> {/* TODO: Fetch and display customer name */}
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Contact ID</p>
            <p>{quoteData.contact}</p> {/* TODO: Fetch and display contact name */}
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Mode</p>
            <p>{quoteData.mode}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Type</p>
            <p>{quoteData.shipment_type}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Origin</p>
            <p>{quoteData.origin_code}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Destination</p>
            <p>{quoteData.destination_code}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Incoterm</p>
            <p>{quoteData.incoterm || "-"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Payment Term</p>
            <p>{quoteData.payment_term}</p>
          </div>
          <div>
             <p className="text-sm font-medium text-muted-foreground">Valid Until</p>
             <p>{formatDate(quoteData.valid_until)}</p>
           </div>
           <div>
             <p className="text-sm font-medium text-muted-foreground">Quote Currency</p>
             <p>{quoteData.output_currency}</p>
           </div>
        </CardContent>
      </Card>

      {/* --- Lines Table Card --- */}
      <Card>
        <CardHeader>
          <CardTitle>Charges</CardTitle>
          <CardDescription>Breakdown of calculated charges for version {version.version_number}.</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="text-right">Sell Price ({quoteData.output_currency})</TableHead>
                <TableHead className="text-right">Incl. GST ({quoteData.output_currency})</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {version.lines.length === 0 ? (
                 <TableRow>
                   <TableCell colSpan={5} className="h-24 text-center">
                     No charge lines found for this version.
                   </TableCell>
                 </TableRow>
              ) : (
                version.lines.map((line) => (
                  <TableRow key={line.id}>
                    <TableCell className="font-medium">{line.service_component?.name || "N/A"}</TableCell>
                    <TableCell>{line.service_component?.category || "N/A"}</TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(line.sell_fcy, quoteData.output_currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(line.sell_fcy_incl_gst, quoteData.output_currency)}
                    </TableCell>
                    <TableCell>
                      {line.is_rate_missing && <Badge variant="destructive">Missing Rate</Badge>}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* --- Totals Card --- */}
      <Card>
         <CardHeader>
           <CardTitle>Totals</CardTitle>
         </CardHeader>
         <CardContent className="space-y-2 text-right">
           {/* TODO: Add Subtotal and GST breakdown if needed */}
           <Separator />
           <div className="flex justify-end items-center space-x-4 pt-2">
             <span className="text-lg font-semibold">Grand Total (Incl. GST):</span>
             <span className="text-xl font-bold">
               {formatCurrency(version.totals.total_sell_fcy_incl_gst, quoteData.output_currency)}
             </span>
             <span className="text-lg font-semibold">{quoteData.output_currency}</span>
           </div>
           {version.totals.has_missing_rates && (
             <p className="text-sm font-semibold text-destructive">
               Note: Total is incomplete due to missing rates.
             </p>
           )}
           {version.totals.notes && (
             <p className="text-sm text-muted-foreground text-left">Notes: {version.totals.notes}</p>
           )}
         </CardContent>
       </Card>

    </div>
  );
}
