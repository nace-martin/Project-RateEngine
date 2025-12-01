"use client";

import { QuoteComputeResult, SellLine } from "@/lib/types";
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

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult;
}

const formatCurrency = (amountStr: string | undefined, currency: string) => {
    const amount = parseFloat(amountStr || "0");
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency,
    }).format(amount);
};

const formatPercent = (percentStr: string | undefined) => {
    const percent = parseFloat(percentStr || "0");
    return `${percent.toFixed(1)}%`;
};

export default function QuoteFinancialBreakdown({ result }: QuoteFinancialBreakdownProps) {
    const { sell_lines, totals, exchange_rates } = result;
    const sellCurrency = totals.currency;

    return (
        <Card className="overflow-hidden">
            <CardHeader className="bg-muted/30 pb-4">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-2xl font-bold text-primary">Financial Breakdown</CardTitle>
                        <CardDescription>
                            Detailed sell-side calculation (Computed: {result.computation_date})
                        </CardDescription>
                    </div>
                    <div className="flex gap-2">
                        {Object.entries(exchange_rates).map(([pair, rate]) => (
                            <Badge key={pair} variant="outline" className="text-xs font-mono">
                                {pair}: {rate}
                            </Badge>
                        ))}
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-6">
                <div className="rounded-lg border shadow-sm overflow-hidden mb-6">
                    <Table>
                        <TableHeader className="bg-muted/50">
                            <TableRow>
                                <TableHead className="w-[100px]">Type</TableHead>
                                <TableHead>Component</TableHead>
                                <TableHead>Description</TableHead>
                                <TableHead className="text-right">Cost (PGK)</TableHead>
                                <TableHead className="text-right">Margin</TableHead>
                                <TableHead className="text-right">Sell (PGK)</TableHead>
                                <TableHead className="text-right">FX Rate</TableHead>
                                <TableHead className="text-right font-bold">Sell ({sellCurrency})</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {sell_lines.map((line: SellLine, index: number) => (
                                <TableRow key={index} className="hover:bg-muted/30">
                                    <TableCell>
                                        <Badge variant={line.line_type === 'CAF' ? 'secondary' : 'outline'}>
                                            {line.line_type}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="font-medium text-muted-foreground">
                                        {line.component || '-'}
                                    </TableCell>
                                    <TableCell>{line.description}</TableCell>
                                    <TableCell className="text-right font-mono text-muted-foreground">
                                        {formatCurrency(line.cost_pgk, 'PGK')}
                                    </TableCell>
                                    <TableCell className="text-right font-mono text-xs">
                                        {parseFloat(line.margin_percent) > 0 && (
                                            <span className="text-green-600 font-medium">
                                                {formatPercent(line.margin_percent)}
                                            </span>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-right font-mono">
                                        {formatCurrency(line.sell_pgk, 'PGK')}
                                    </TableCell>
                                    <TableCell className="text-right font-mono text-xs text-muted-foreground">
                                        {line.exchange_rate}
                                    </TableCell>
                                    <TableCell className="text-right font-mono font-bold text-foreground">
                                        {formatCurrency(line.sell_fcy, line.sell_currency)}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>

                <div className="flex justify-end">
                    <div className="bg-muted/30 p-6 rounded-lg w-full max-w-md">
                        <div className="flex flex-col space-y-3">
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total Cost (PGK)</span>
                                <span className="font-mono">{formatCurrency(totals.cost_pgk, 'PGK')}</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total Sell (PGK)</span>
                                <span className="font-mono">{formatCurrency(totals.sell_pgk, 'PGK')}</span>
                            </div>
                            {parseFloat(totals.caf_pgk) > 0 && (
                                <div className="flex justify-between text-sm text-blue-600">
                                    <span>Includes CAF (PGK)</span>
                                    <span className="font-mono">{formatCurrency(totals.caf_pgk, 'PGK')}</span>
                                </div>
                            )}
                            <Separator className="my-2" />
                            <div className="flex justify-between items-end">
                                <span className="text-base font-semibold text-foreground">Total Quote Amount</span>
                                <div className="text-right">
                                    <span className="block text-3xl font-bold text-primary tracking-tight">
                                        {formatCurrency(totals[`sell_${sellCurrency.toLowerCase()}`], sellCurrency)}
                                    </span>
                                    <span className="text-xs text-muted-foreground uppercase font-medium">{sellCurrency}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
