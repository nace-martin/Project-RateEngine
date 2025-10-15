import { BuyOffer } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";

interface QuoteResultDisplayProps {
  result: BuyOffer;
}

// Helper to format currency
const formatCurrency = (amount: number, currency: string) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
  }).format(amount);
};

export default function QuoteResultDisplay({ result }: QuoteResultDisplayProps) {
  // Calculate the total freight cost and total fees
  const freightTotal = (result.breaks || []).reduce((acc, item) => acc + (item.total || 0), 0);
  const feesTotal = (result.fees || []).reduce((acc, fee) => acc + fee.rate, 0);
  const grandTotal = freightTotal + feesTotal;

  // In our current logic, the 'from_kg' of the first break represents the chargeable weight
  const chargeableWeight = result.breaks[0]?.from_kg || 0;

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Cost Calculation Result</CardTitle>
        <CardDescription>
          {`Quote for ${result.lane.origin} to ${result.lane.dest}`}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex justify-between items-center mb-4">
          <span className="text-lg font-medium">Total Cost</span>
          <span className="text-2xl font-bold text-primary">
            {formatCurrency(grandTotal, result.ccy)}
          </span>
        </div>
        <Separator />
        <div className="mt-4">
          <p className="mb-2">
            <strong>Chargeable Weight:</strong> {chargeableWeight.toFixed(2)} kg
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>Base Freight</TableCell>
                <TableCell className="text-right font-medium">
                  {formatCurrency(freightTotal, result.ccy)}
                </TableCell>
              </TableRow>
              {result.fees.map((fee, index) => (
                <TableRow key={index}>
                  <TableCell>{fee.code}</TableCell>
                  <TableCell className="text-right">
                    {formatCurrency(fee.rate, result.ccy)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}