"use client";

import { useState } from "react";
import { QuoteComputeResult, SellLine } from "@/lib/types";
import {
    Card,
    CardContent,
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
import { ChevronDown, ChevronRight, Package, MapPin, ReceiptText } from "lucide-react";

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult;
}

const formatCurrency = (amountStr: string | number | undefined, currency: string) => {
    const amount = typeof amountStr === 'number' ? amountStr : parseFloat(amountStr || "0");
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency,
    }).format(amount);
};

// Simplified currency display without symbol (for cleaner table display)
const formatAmount = (amountStr: string | number | undefined, currency: string) => {
    const amount = typeof amountStr === 'number' ? amountStr : parseFloat(amountStr || "0");
    const formatted = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(amount);
    return `${currency} ${formatted}`;
};

type BucketType = 'ORIGIN' | 'DESTINATION';

// Get bucket for a line
function getBucket(line: SellLine): BucketType {
    if (line.leg === 'ORIGIN' || line.leg === 'MAIN') return 'ORIGIN';
    return 'DESTINATION';
}

// Calculate bucket subtotal
function calculateBucketTotal(lines: SellLine[], field: 'sell_pgk_incl_gst' | 'sell_pgk' | 'sell_fcy' | 'sell_fcy_incl_gst'): number {
    return lines.reduce((sum, line) => {
        const value = parseFloat(line[field] || '0');
        return sum + value;
    }, 0);
}

// Determine if lines are FCY passthrough
function isFCYPassthrough(lines: SellLine[]): boolean {
    if (lines.length === 0) return false;
    const totalPgk = calculateBucketTotal(lines, 'sell_pgk');
    const totalFcy = calculateBucketTotal(lines, 'sell_fcy');
    return totalPgk === 0 && totalFcy > 0;
}

export default function QuoteFinancialBreakdown({ result }: QuoteFinancialBreakdownProps) {
    const { sell_lines, totals } = result;
    const sellCurrency = totals.currency;

    // Detect if this is an FCY passthrough quote
    const isOverallPassthrough = isFCYPassthrough(sell_lines);
    const displayCurrency = isOverallPassthrough ? (sell_lines[0]?.sell_currency || 'PGK') : 'PGK';

    // Group lines by bucket (Origin includes Freight, Destination separate)
    const buckets: Record<BucketType, SellLine[]> = {
        ORIGIN: [],
        DESTINATION: [],
    };

    sell_lines.forEach((line: SellLine) => {
        const bucket = getBucket(line);
        buckets[bucket].push(line);
    });

    // Calculate totals
    const totalExGst = isOverallPassthrough
        ? calculateBucketTotal(sell_lines, 'sell_fcy')
        : calculateBucketTotal(sell_lines, 'sell_pgk');
    const totalGst = isOverallPassthrough
        ? 0 // No GST for passthrough
        : sell_lines.reduce((sum, l) => sum + parseFloat(l.gst_amount || '0'), 0);
    const totalIncGst = totalExGst + totalGst;

    return (
        <Card className="overflow-hidden border-slate-200">
            <CardHeader className="pb-4 border-b border-slate-100">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-lg font-semibold flex items-center gap-2">
                        <ReceiptText className="w-5 h-5 text-slate-400" />
                        Financial Breakdown
                    </CardTitle>
                    <span className="text-xs text-slate-400">
                        Computed {result.computation_date}
                    </span>
                </div>
            </CardHeader>
            <CardContent className="p-0">
                {/* ORIGIN CHARGES */}
                {buckets.ORIGIN.length > 0 && (
                    <BucketSection
                        title="Origin Charges"
                        lines={buckets.ORIGIN}
                        displayCurrency={displayCurrency}
                        isPassthrough={isOverallPassthrough}
                        icon={<Package className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
                    />
                )}

                {/* DESTINATION CHARGES */}
                {buckets.DESTINATION.length > 0 && (
                    <BucketSection
                        title="Destination Charges"
                        lines={buckets.DESTINATION}
                        displayCurrency={displayCurrency}
                        isPassthrough={isOverallPassthrough}
                        icon={<MapPin className="w-4 h-4 text-emerald-600" />}
                        colorClass="emerald"
                    />
                )}

                {/* Totals Section */}
                <div className="p-6 bg-slate-50 border-t border-slate-200">
                    <div className="flex flex-col items-end space-y-2">
                        <div className="flex justify-between w-full max-w-xs text-sm">
                            <span className="text-slate-500">Total Sell (Ex GST)</span>
                            <span className="font-mono font-medium">
                                {formatAmount(totalExGst, displayCurrency)}
                            </span>
                        </div>
                        <div className="flex justify-between w-full max-w-xs text-sm">
                            <span className="text-slate-500">Total GST</span>
                            <span className="font-mono">
                                {formatAmount(totalGst, displayCurrency)}
                            </span>
                        </div>
                        <Separator className="w-full max-w-xs my-2" />
                        <div className="flex justify-between w-full max-w-xs items-end">
                            <span className="text-sm font-medium text-slate-700">Total Quote Amount</span>
                            <div className="text-right">
                                <span className="block text-2xl font-bold text-blue-600">
                                    {displayCurrency} {totalIncGst.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                </span>
                                <span className="text-[10px] text-slate-400 uppercase">
                                    {displayCurrency} (INC GST)
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

// Bucket Section Component
function BucketSection({
    title,
    lines,
    displayCurrency,
    isPassthrough,
    icon,
    colorClass
}: {
    title: string;
    lines: SellLine[];
    displayCurrency: string;
    isPassthrough: boolean;
    icon: React.ReactNode;
    colorClass: 'blue' | 'emerald';
}) {
    const [isExpanded, setIsExpanded] = useState(true);

    // Calculate bucket subtotal
    const bucketTotal = isPassthrough
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    const bgColor = colorClass === 'blue' ? 'bg-blue-50' : 'bg-emerald-50';
    const textColor = colorClass === 'blue' ? 'text-blue-700' : 'text-emerald-700';
    const badgeClass = colorClass === 'blue'
        ? 'bg-blue-100 text-blue-600 border-blue-200'
        : 'bg-emerald-100 text-emerald-600 border-emerald-200';

    return (
        <div className="border-b border-slate-100 last:border-b-0">
            {/* Bucket Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full ${bgColor} px-6 py-3 flex items-center justify-between hover:opacity-90 transition-opacity`}
            >
                <div className="flex items-center gap-2">
                    {icon}
                    <span className={`font-semibold text-sm uppercase tracking-wide ${textColor}`}>
                        {title}
                    </span>
                    <Badge variant="outline" className={`text-[10px] ${badgeClass} ml-2`}>
                        {lines.length} items
                    </Badge>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-500 uppercase">Subtotal</span>
                    <span className={`font-bold font-mono ${textColor}`}>
                        {formatAmount(bucketTotal, displayCurrency)}
                    </span>
                    {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                </div>
            </button>

            {/* Bucket Content */}
            {isExpanded && (
                <div className="bg-white">
                    <Table>
                        <TableHeader>
                            <TableRow className="border-b border-slate-100 hover:bg-transparent">
                                <TableHead className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold w-[45%]">
                                    Description
                                </TableHead>
                                <TableHead className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold text-right">
                                    Sell (Ex GST)
                                </TableHead>
                                <TableHead className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold text-right">
                                    GST
                                </TableHead>
                                <TableHead className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold text-right">
                                    Total
                                </TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {lines.map((line, index) => (
                                <ChargeRow
                                    key={index}
                                    line={line}
                                    displayCurrency={displayCurrency}
                                    isPassthrough={isPassthrough}
                                />
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </div>
    );
}

// Individual Charge Row
function ChargeRow({
    line,
    displayCurrency,
    isPassthrough
}: {
    line: SellLine;
    displayCurrency: string;
    isPassthrough: boolean;
}) {
    const sellExGst = isPassthrough ? line.sell_fcy : line.sell_pgk;
    const gstAmount = isPassthrough ? '0' : line.gst_amount;
    const total = isPassthrough
        ? line.sell_fcy
        : (line.sell_pgk_incl_gst || line.sell_pgk);

    return (
        <TableRow className="hover:bg-slate-50/50 border-b border-slate-50">
            <TableCell className="py-3">
                <div className="font-medium text-slate-800 text-sm">
                    {line.description}
                </div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">
                    {line.component || 'MISC'}
                </div>
            </TableCell>
            <TableCell className="text-right font-mono text-sm text-slate-600">
                {formatAmount(sellExGst, displayCurrency)}
            </TableCell>
            <TableCell className="text-right font-mono text-sm text-slate-400">
                {parseFloat(gstAmount || '0') > 0
                    ? formatAmount(gstAmount, displayCurrency)
                    : '—'
                }
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-semibold text-slate-800">
                {formatAmount(total, displayCurrency)}
            </TableCell>
        </TableRow>
    );
}
