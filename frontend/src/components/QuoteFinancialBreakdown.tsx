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
import { ChevronDown, ChevronRight, Package, MapPin, ReceiptText, Plane } from "lucide-react";

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult;
}

type BreakdownScalar = string | number | boolean | null | undefined;
type BreakdownLine = SellLine & Record<string, BreakdownScalar>;
type BreakdownTotals = Record<string, BreakdownScalar> & QuoteComputeResult["totals"];
type BreakdownDataShape = {
    latest_version?: {
        sell_lines?: BreakdownLine[];
        lines?: BreakdownLine[];
        totals?: BreakdownTotals;
    };
    sell_lines?: BreakdownLine[];
    lines?: BreakdownLine[];
    totals?: BreakdownTotals;
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


type BucketType = 'ORIGIN' | 'FREIGHT' | 'DESTINATION';

// Get bucket for a line
function getBucket(line: SellLine): BucketType {
    if (line.leg === 'MAIN' || line.leg === 'FREIGHT') return 'FREIGHT';
    if (line.leg === 'ORIGIN') return 'ORIGIN';
    return 'DESTINATION';
}

// Calculate bucket subtotal
function calculateBucketTotal(lines: BreakdownLine[], field: string): number {
    return lines.reduce((sum, line) => {
        // Handle field aliases (e.g., sell_pgk vs total_sell_pgk)
        const rawValue = line[field];
        const value = parseFloat(String(rawValue ?? '0'));
        return sum + value;
    }, 0);
}


export default function QuoteFinancialBreakdown({ result }: QuoteFinancialBreakdownProps) {
    // BACKWARD COMPATIBILITY FIX: 
    // If we receive a full Quote object (V3), map its latest_version to the expected fields
    const normalizedResult = result as unknown as BreakdownDataShape;
    const data = normalizedResult.latest_version ?? normalizedResult;
    const sell_lines: BreakdownLine[] = data.sell_lines || data.lines || [];
    const totals = data.totals;

    // Detect display currency and logic flags
    const firstLineCurrency = sell_lines[0]?.sell_fcy_currency || sell_lines[0]?.sell_currency || 'PGK';
    const displayCurrency = totals?.currency || totals?.total_sell_fcy_currency || firstLineCurrency;
    const isShowingFCY = displayCurrency !== 'PGK';

    // Separate informational (conditional) charges from priced lines
    const pricedLines = sell_lines.filter((line) => !line.is_informational);
    const informationalLines = sell_lines.filter((line) => line.is_informational);

    // Group PRICED lines by bucket (not informational ones)
    const buckets: Record<BucketType, SellLine[]> = {
        ORIGIN: [],
        FREIGHT: [],
        DESTINATION: [],
    };

    pricedLines.forEach((line: SellLine) => {
        const bucket = getBucket(line);
        buckets[bucket].push(line);
    });

    // 3. Robust Total Mapping - Exhaustive check of all possible backend field names
    const totalExGst = isShowingFCY
        ? parseFloat(totals?.total_sell_ex_gst || totals?.total_sell_fcy || totals?.sell_fcy || '0')
        : parseFloat(totals?.total_sell_pgk || totals?.sell_pgk || '0');
        
    const totalGst = parseFloat(totals?.gst_amount || totals?.total_gst || totals?.gst_pgk || '0');
    
    const totalIncGst = isShowingFCY
        ? parseFloat(totals?.total_quote_amount || totals?.total_sell_fcy_incl_gst || totals?.sell_fcy_incl_gst || totals?.total_sell_fcy || '0')
        : parseFloat(totals?.total_sell_pgk_incl_gst || totals?.sell_pgk_incl_gst || totals?.sell_pgk || '0');



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
                        isShowingFCY={isShowingFCY}
                        icon={<Package className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
                    />
                )}
                {/* FREIGHT CHARGES */}
                {buckets.FREIGHT.length > 0 && (
                    <BucketSection
                        title="Freight Charges"
                        lines={buckets.FREIGHT}
                        displayCurrency={displayCurrency}
                        isShowingFCY={isShowingFCY}
                        icon={<Plane className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
                    />
                )}

                {/* DESTINATION CHARGES */}
                {buckets.DESTINATION.length > 0 && (
                    <BucketSection
                        title="Destination Charges"
                        lines={buckets.DESTINATION}
                        displayCurrency={displayCurrency}
                        isShowingFCY={isShowingFCY}
                        icon={<MapPin className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
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

                {/* Conditional Charges Footnotes */}
                {informationalLines.length > 0 && (
                    <div className="p-4 bg-amber-50/50 border-t border-amber-200">
                        <div className="flex items-start gap-2">
                            <span className="text-amber-600 text-xs font-semibold uppercase tracking-wide">Conditions & Notes</span>
                        </div>
                        <ul className="mt-2 space-y-1">
                            {informationalLines.map((line, idx) => (
                                <li key={idx} className="text-xs text-amber-800 flex items-start gap-2">
                                    <span className="text-amber-500">•</span>
                                    <span>{line.description} — <em className="text-amber-600">if applicable</em></span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

// Helper for section styling - Refined for visual hierarchy & lighter feel
function getSectionStyle() {
    return {
        wrapper: "mb-6 rounded-lg border border-slate-200 overflow-hidden bg-white shadow-sm", // Clean card style
        header: "bg-white hover:bg-slate-50 border-b border-slate-100 transition-colors", // Lighter header
        title: "text-slate-900", // Stronger title contrast
        iconBg: "bg-blue-50 text-blue-600", // Subtler icon background
        borderLeft: "border-l-[4px] border-l-blue-500" // Consistent accent
    };
}

// Bucket Section Component
function BucketSection({
    title,
    lines,
    displayCurrency,
    isShowingFCY,
    icon,
    // colorClass prop is present in parent but ignored here to enforce standardized Blue theme
}: {
    title: string;
    lines: BreakdownLine[];
    displayCurrency: string;
    isShowingFCY: boolean;
    icon: React.ReactNode;
    colorClass?: string;
}) {
    // Default to collapsed for Freight/Dest, maybe Expanded for Origin? 
    // User requested default collapsed previously.
    const [isExpanded, setIsExpanded] = useState(false);
    const styles = getSectionStyle();

    // Calculate subtotal for this bucket
    const bucketTotal = isShowingFCY
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    return (
        <div className={styles.wrapper}>
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full flex items-center justify-between p-5 ${styles.header} ${styles.borderLeft}`}
            >
                <div className="flex items-center gap-4">
                    <div className={`p-2 rounded-lg ${styles.iconBg}`}>
                        {icon}
                    </div>
                    <div className="text-left">
                        <div className="flex items-center gap-3">
                            <h3 className={`text-base font-bold tracking-tight ${styles.title}`}>
                                {title}
                            </h3>
                            {!isExpanded && (
                                <span className="flex items-center justify-center bg-slate-100 text-slate-500 text-[11px] font-semibold h-6 px-2 rounded-full">
                                    {lines.length}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-0.5">Subtotal</p>
                        <p className="text-base font-bold text-slate-900 mono-font">
                            {formatAmount(bucketTotal, displayCurrency)}
                        </p>
                    </div>
                    {isExpanded ? (
                        <ChevronDown className="w-5 h-5 text-slate-400" />
                    ) : (
                        <ChevronRight className="w-5 h-5 text-slate-400" />
                    )}
                </div>
            </button>

            {isExpanded && (
                <div className="p-6 pt-2 bg-slate-50/30">
                    <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                        <Table>
                            <TableHeader className="bg-slate-50/80">
                                <TableRow className="hover:bg-transparent border-b border-slate-100">
                                    <TableHead className="w-[50%] h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500 pl-6">Description</TableHead>
                                    <TableHead className="text-right h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500">Sell (Ex GST)</TableHead>
                                    <TableHead className="text-center h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500 w-[120px]">GST</TableHead>
                                    <TableHead className="text-right h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500 pr-6">Total</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {lines.map((line, index: number) => (
                                    <ChargeRow
                                        key={index}
                                        line={line}
                                        displayCurrency={displayCurrency}
                                        isShowingFCY={isShowingFCY}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </div>
            )}
        </div>
    );
}

// Individual Charge Row
function ChargeRow({
    line,
    displayCurrency,
    isShowingFCY
}: {
    line: BreakdownLine;
    displayCurrency: string;
    isShowingFCY: boolean;
}) {
    // Robust line mapping
    const sellExGst = isShowingFCY 
        ? (line.sell_fcy || line.sell_pgk) 
        : (line.sell_pgk || line.sell_fcy);
        
    const gstAmountVal = parseFloat(line.gst_amount || '0');

    // Determine GST display text
    let gstDisplay: React.ReactNode = '—';
    if (gstAmountVal > 0) {
        gstDisplay = formatAmount(gstAmountVal, displayCurrency);
    } else {
        // Updated to non-interactive muted text
        gstDisplay = <span className="text-[10px] font-medium text-slate-400 uppercase tracking-wide">Exempt</span>;
    }

    const total = isShowingFCY
        ? (line.sell_fcy_incl_gst || line.sell_fcy)
        : (line.sell_pgk_incl_gst || line.sell_pgk || line.sell_fcy_incl_gst);

    return (
        <TableRow className="hover:bg-blue-50/30 border-b border-slate-50 last:border-0 transition-colors">
            <TableCell className="py-4 pl-6">
                <div className="font-medium text-slate-700 text-sm">
                    {line.description}
                </div>
                {/* Reduced emphasis on line codes - secondary info */}
                <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-1 font-mono opacity-80">
                    {line.component || 'MISC'}
                </div>
            </TableCell>
            <TableCell className="text-right font-mono text-sm text-slate-600 py-4">
                {formatAmount(sellExGst, displayCurrency)}
            </TableCell>
            <TableCell className="text-center py-4">
                {/* GST Column centered and clean */}
                <div className="flex items-center justify-center">
                    {gstDisplay}
                </div>
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-bold text-slate-800 py-4 pr-6">
                {formatAmount(total, displayCurrency)}
            </TableCell>
        </TableRow>
    );
}
