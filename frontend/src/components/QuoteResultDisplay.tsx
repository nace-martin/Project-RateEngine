"use client";

import { V3QuoteComputeResponse, V3QuoteLine } from "@/lib/types";
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
    <Card className="overflow-hidden">
      <CardHeader className="bg-muted/30 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-2xl font-bold text-primary">Quote Summary</CardTitle>
            <CardDescription>Final breakdown and totals</CardDescription>
          </div>
          {totals.has_missing_rates && (
            <Badge variant="destructive" className="text-sm px-3 py-1">
              Incomplete
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-6">
        <div className="mb-8 grid grid-cols-2 gap-6 md:grid-cols-4">
          <InfoBox label="Status" value={quote.status} />
          <InfoBox label="Incoterm" value={quote.incoterm} />
          <InfoBox label="Payment Term" value={quote.payment_term} />
          {quote.valid_until && !['DRAFT', 'INCOMPLETE'].includes(quote.status) && (
            <InfoBox
              label="Valid Until"
              value={new Date(quote.valid_until).toLocaleDateString()}
            />
          )}
        </div>

        <div className="space-y-8">
          <ChargeSection title="Origin Charges" lines={version.lines.filter(l => (l.service_component?.leg || 'MAIN') === 'ORIGIN')} currency={currency} />
          <ChargeSection title="Freight Charges" lines={version.lines.filter(l => ['MAIN', 'FREIGHT'].includes(l.service_component?.leg || 'MAIN'))} currency={currency} />
          <ChargeSection title="Destination Charges" lines={version.lines.filter(l => (l.service_component?.leg || 'MAIN') === 'DESTINATION')} currency={currency} />

          {/* Catch-all for any others */}
          {version.lines.some(l => !['ORIGIN', 'MAIN', 'FREIGHT', 'DESTINATION'].includes(l.service_component?.leg || 'MAIN')) && (
            <ChargeSection
              title="Other Charges"
              lines={version.lines.filter(l => !['ORIGIN', 'MAIN', 'FREIGHT', 'DESTINATION'].includes(l.service_component?.leg || 'MAIN'))}
              currency={currency}
            />
          )}
        </div>
      </CardContent>

      <div className="bg-muted/30 p-6">
        <div className="flex flex-col items-end space-y-3">
          <div className="flex w-full max-w-sm justify-between text-sm">
            <span className="text-muted-foreground">Total (Excl. GST)</span>
            <span className="font-medium font-mono">
              {formatCurrency(totals.total_sell_fcy, currency)}
            </span>
          </div>
          <div className="flex w-full max-w-sm justify-between text-sm">
            <span className="text-muted-foreground">GST</span>
            <span className="font-medium font-mono">
              {formatCurrency(
                (parseFloat(totals.total_sell_fcy_incl_gst || "0") - parseFloat(totals.total_sell_fcy || "0")).toString(),
                currency
              )}
            </span>
          </div>
          <Separator className="my-2 w-full max-w-sm" />
          <div className="flex w-full max-w-sm justify-between items-end">
            <span className="text-base font-semibold text-foreground">Total Amount</span>
            <div className="text-right">
              <span className="block text-3xl font-bold text-primary tracking-tight">
                {formatCurrency(totals.total_sell_fcy_incl_gst, currency)}
              </span>
              <span className="text-xs text-muted-foreground uppercase font-medium">{currency}</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}

function ChargeSection({ title, lines, currency }: { title: string, lines: V3QuoteLine[], currency: string }) {
  if (lines.length === 0) return null;

  return (
    <div className="rounded-lg border shadow-sm overflow-hidden">
      <div className="bg-muted/50 px-4 py-2 border-b">
        <h3 className="font-semibold text-sm uppercase tracking-wider text-muted-foreground">{title}</h3>
      </div>
      <Table>
        <TableHeader className="bg-muted/20">
          <TableRow>
            <TableHead className="w-[150px]">Category</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="text-right">Sell (Ex. GST)</TableHead>
            <TableHead className="text-right">Sell (Inc. GST)</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {lines.map((line) => (
            <TableRow key={line.id} className="hover:bg-muted/30">
              <TableCell className="font-medium text-muted-foreground">
                {line.service_component?.category || 'Manual'}
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  {line.cost_source_description || line.service_component?.description || 'Spot Charge'}
                  {line.is_rate_missing && (
                    <Badge variant="destructive" className="text-[10px] h-5 px-1.5">
                      Missing
                    </Badge>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-right font-mono text-foreground">
                {formatCurrency(line.sell_fcy, currency)}
              </TableCell>
              <TableCell className="text-right font-mono font-medium text-foreground">
                {formatCurrency(line.sell_fcy_incl_gst, currency)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
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
