"use client";

import { V3QuoteComputeResponse, V3QuoteLine } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
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
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";

// Define the new props interface
interface QuoteResultDisplayProps {
  quote: V3QuoteComputeResponse;
}

// Helper to format currency.
// The backend sends strings, but we'll parse them to format consistently.
const formatCurrency = (amountStr: string | null | undefined, currency: string) => {
  const amount = parseFloat(amountStr || "0");
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
  }).format(amount);
};

export default function QuoteResultDisplay({ quote }: QuoteResultDisplayProps) {
  // Get the latest version and its totals
  const version = quote.latest_version;
  const totals = version.totals;
  const currency = totals.total_sell_fcy_currency;

  return (
    <div className="container mx-auto max-w-4xl p-4">
      <Card className="mt-6">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-3xl">
              Quote: {quote.quote_number}
            </CardTitle>
            {totals.has_missing_rates && (
              <Badge variant="destructive" className="text-base">
                Incomplete - Missing Rates
              </Badge>
            )}
          </div>
          <CardDescription className="text-lg">
            {quote.origin_airport} to {quote.destination_airport} ({quote.mode})
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            <InfoBox label="Status" value={quote.status} />
            <InfoBox label="Incoterm" value={quote.incoterm} />
            <InfoBox label="Payment Term" value={quote.payment_term} />
            <InfoBox
              label="Valid Until"
              value={new Date(quote.valid_until).toLocaleDateString()}
            />
          </div>

          <Separator />

          <div className="mt-6">
            <h3 className="mb-4 text-xl font-semibold">Charges</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Category</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Sell (Ex. GST)</TableHead>
                  <TableHead className="text-right">Sell (Inc. GST)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {version.lines.map((line: V3QuoteLine) => (
                  <TableRow key={line.id}>
                    <TableCell>
                      {line.service_component.category}
                    </TableCell>
                    <TableCell>
                      {line.service_component.description}
                      {line.is_rate_missing && (
                         <Badge variant="outline" className="ml-2">Missing</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(line.sell_fcy, currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatCurrency(line.sell_fcy_incl_gst, currency)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>

        <Separator />

        <CardFooter className="mt-6 flex flex-col items-end space-y-2">
          <div className="flex w-full max-w-sm justify-between">
            <span className="text-muted-foreground">Total (Excl. GST)</span>
            <span className="font-medium">
              {formatCurrency(totals.total_sell_fcy, currency)}
            </span>
          </div>
          <div className="flex w-full max-w-sm justify-between text-2xl font-bold">
            <span className="text-primary">Total (Incl. GST)</span>
            <span className="text-primary">
              {formatCurrency(totals.total_sell_fcy_incl_gst, currency)}
            </span>
          </div>
          <div className="flex w-full max-w-sm justify-between">
            <span className="text-muted-foreground">Currency</span>
            <span className="font-medium">{currency}</span>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}

// A small helper component for the info boxes
function InfoBox({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-lg font-semibold">{value || "---"}</dd>
    </div>
  );
}
