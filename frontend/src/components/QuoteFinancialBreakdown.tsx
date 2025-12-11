"use client";

import { useState } from "react";
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
import { ChevronDown, ChevronRight, Package, Plane, MapPin } from "lucide-react";

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

const formatPercent = (percentStr: string | undefined) => {
    const percent = parseFloat(percentStr || "0");
    return `${percent.toFixed(1)}%`;
};

// ============================================================
// BUCKET DEFINITIONS - Maps components to buckets
// ============================================================
type BucketType = 'ORIGIN' | 'FREIGHT' | 'DESTINATION';

const BUCKET_CONFIG: Record<BucketType, {
    title: string;
    icon: React.ComponentType<{ className?: string }>;
    colorClass: string;  // Tailwind border/text color
    bgClass: string;     // Tailwind background color
    badgeClass: string;  // Badge styling
}> = {
    ORIGIN: {
        title: 'Origin Charges',
        icon: Package,
        colorClass: 'border-blue-500 text-blue-700',
        bgClass: 'bg-blue-50',
        badgeClass: 'bg-blue-100 text-blue-700 border-blue-200',
    },
    FREIGHT: {
        title: 'Freight Charges',
        icon: Plane,
        colorClass: 'border-purple-500 text-purple-700',
        bgClass: 'bg-purple-50',
        badgeClass: 'bg-purple-100 text-purple-700 border-purple-200',
    },
    DESTINATION: {
        title: 'Destination Charges',
        icon: MapPin,
        colorClass: 'border-emerald-500 text-emerald-700',
        bgClass: 'bg-emerald-50',
        badgeClass: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    },
};

// Component codes that map to each bucket
// Component codes that map to each bucket
const ORIGIN_COMPONENTS = [
    'AGENCY_EXP', 'AWB_FEE', 'DOC_EXP', 'CTO', 'XRAY',
    'PICKUP', 'PICKUP_FUEL', 'STORAGE_EXP', 'FUMIGATION',
    // Export Specifics
    'DOC_EXP_AWB', 'DOC_EXP_BIC', 'DOC_EXP_LCC',
    'HND_EXP_BSC', 'HND_EXP_VA', 'SEC_EXP_MXC', 'HND_EXP_BPC', 'HND_EXP_RAC',
    'CLEAR_EXP', 'CUS_ENTRY_EXP', 'PICKUP_EXP', 'FUEL_SURCHARGE_EXP'
];

const FREIGHT_COMPONENTS = [
    'FRT_AIR', 'FRT_AIR_EXP', 'FRT_SEA_LCL', 'FRT_SEA_FCL',
    'FRT_ROAD', 'FUEL_SURCHARGE', 'SECURITY_SURCHARGE'
];

const DESTINATION_COMPONENTS = [
    'AGENCY_IMP', 'CLEARANCE', 'DOC_IMP', 'HANDLING',
    'TERM_INT', 'CARTAGE', 'CARTAGE_FUEL', 'STORAGE_IMP',
    'DST_CHARGES', 'DST-CLEAR-CUS', 'DST-DELIV-STD',
    'DST-HANDL-STD', 'DST-DOC-IMP', 'DST-AGENCY-IMP', 'DST-TERM-INTL'
];

// Subgroup definitions within each bucket
interface ChargeSubgroup {
    title: string;
    order: number;
    codes: string[];
}

const ORIGIN_SUBGROUPS: Record<string, ChargeSubgroup> = {
    'documentation': {
        title: 'Documentation & Compliance',
        order: 1,
        codes: ['DOC_EXP', 'AGENCY_EXP', 'AWB_FEE', 'DOC_EXP_AWB', 'DOC_EXP_BIC', 'DOC_EXP_LCC', 'CLEAR_EXP', 'CUS_ENTRY_EXP']
    },
    'terminal': {
        title: 'Terminal & Handling',
        order: 2,
        codes: ['HND_EXP_BSC', 'HND_EXP_VA', 'SEC_EXP_MXC', 'HND_EXP_BPC', 'HND_EXP_RAC']
    },
    'inspection': {
        title: 'Inspection & Security',
        order: 3,
        codes: ['XRAY', 'CTO', 'FUMIGATION']
    },
    'collection': {
        title: 'Collection Services',
        order: 4,
        codes: ['PICKUP', 'PICKUP_FUEL', 'STORAGE_EXP', 'PICKUP_EXP', 'FUEL_SURCHARGE_EXP']
    },
};

const FREIGHT_SUBGROUPS: Record<string, ChargeSubgroup> = {
    'transport': {
        title: 'International Transport',
        order: 1,
        codes: ['FRT_AIR', 'FRT_AIR_EXP', 'FRT_SEA_LCL', 'FRT_SEA_FCL', 'FRT_ROAD']
    },
    'surcharges': {
        title: 'Carrier Surcharges',
        order: 2,
        codes: ['FUEL_SURCHARGE', 'SECURITY_SURCHARGE']
    },
};

const DESTINATION_SUBGROUPS: Record<string, ChargeSubgroup> = {
    'customs': {
        title: 'Customs & Regulatory',
        order: 1,
        codes: ['CLEARANCE', 'AGENCY_IMP', 'DST-CLEAR-CUS', 'DST-AGENCY-IMP']
    },
    'handling': {
        title: 'Terminal & Handling',
        order: 2,
        codes: ['DOC_IMP', 'HANDLING', 'TERM_INT', 'DST-HANDL-STD', 'DST-DOC-IMP', 'DST-TERM-INTL', 'DST_CHARGES']
    },
    'delivery': {
        title: 'Delivery Services',
        order: 3,
        codes: ['CARTAGE', 'CARTAGE_FUEL', 'DST-DELIV-STD', 'STORAGE_IMP']
    },
};

// Get bucket for a line (uses leg first, then component code mapping)
function getBucket(line: SellLine): BucketType {
    // First try using the leg field
    if (line.leg === 'ORIGIN') return 'ORIGIN';
    if (line.leg === 'MAIN') return 'FREIGHT';
    if (line.leg === 'DESTINATION') return 'DESTINATION';

    // Fallback to component code mapping
    const code = line.component || '';
    if (ORIGIN_COMPONENTS.includes(code)) return 'ORIGIN';
    if (FREIGHT_COMPONENTS.includes(code)) return 'FREIGHT';
    if (DESTINATION_COMPONENTS.includes(code)) return 'DESTINATION';

    // Default to DESTINATION if unsure
    console.warn(`Unknown component ${code} - defaulting to DESTINATION bucket`);
    return 'DESTINATION';
}

// Get subgroup within a bucket
function getSubgroup(component: string | null | undefined, bucket: BucketType): string {
    if (!component) return 'other';

    const subgroups = bucket === 'ORIGIN' ? ORIGIN_SUBGROUPS
        : bucket === 'FREIGHT' ? FREIGHT_SUBGROUPS
            : DESTINATION_SUBGROUPS;

    for (const [key, config] of Object.entries(subgroups)) {
        if (config.codes.includes(component)) {
            return key;
        }
    }
    return 'other';
}

// Calculate bucket subtotal - handles both PGK and FCY (for passthrough quotes)
function calculateBucketTotal(lines: SellLine[], field: 'sell_pgk_incl_gst' | 'sell_pgk' | 'sell_fcy' | 'sell_fcy_incl_gst'): number {
    return lines.reduce((sum, line) => {
        const value = parseFloat(line[field] || '0');
        return sum + value;
    }, 0);
}

// Determine if lines are FCY passthrough (when sell_pgk = 0 but sell_fcy > 0)
function isFCYPassthrough(lines: SellLine[]): boolean {
    if (lines.length === 0) return false;
    const totalPgk = calculateBucketTotal(lines, 'sell_pgk');
    const totalFcy = calculateBucketTotal(lines, 'sell_fcy');
    return totalPgk === 0 && totalFcy > 0;
}

// Get the sell currency for a set of lines
function getLineCurrency(lines: SellLine[]): string {
    if (lines.length === 0) return 'PGK';
    // Check if any line has sell_currency set (for FCY passthrough)
    const line = lines.find(l => l.sell_currency && l.sell_currency !== 'PGK');
    return line?.sell_currency || 'PGK';
}

// ============================================================
// MAIN COMPONENT
// ============================================================
export default function QuoteFinancialBreakdown({ result }: QuoteFinancialBreakdownProps) {
    const { sell_lines, totals, exchange_rates } = result;
    const sellCurrency = totals.currency;

    // Detect if this is an overall FCY passthrough quote (e.g., A2D DAP PREPAID)
    const isOverallPassthrough = isFCYPassthrough(sell_lines);
    const overallDisplayCurrency = isOverallPassthrough ? getLineCurrency(sell_lines) : 'PGK';

    // Group lines by bucket
    const buckets: Record<BucketType, SellLine[]> = {
        ORIGIN: [],
        FREIGHT: [],
        DESTINATION: [],
    };

    sell_lines.forEach((line: SellLine) => {
        const bucket = getBucket(line);
        buckets[bucket].push(line);
    });

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
            <CardContent className="p-6 space-y-6">
                {/* ORIGIN BUCKET */}
                {buckets.ORIGIN.length > 0 && (
                    <BucketSection
                        bucket="ORIGIN"
                        lines={buckets.ORIGIN}
                        sellCurrency={sellCurrency}
                    />
                )}

                {/* FREIGHT BUCKET */}
                {buckets.FREIGHT.length > 0 && (
                    <BucketSection
                        bucket="FREIGHT"
                        lines={buckets.FREIGHT}
                        sellCurrency={sellCurrency}
                    />
                )}

                {/* DESTINATION BUCKET */}
                {buckets.DESTINATION.length > 0 && (
                    <BucketSection
                        bucket="DESTINATION"
                        lines={buckets.DESTINATION}
                        sellCurrency={sellCurrency}
                    />
                )}

                {/* QUOTE SUMMARY */}
                <div className="flex justify-end mt-6">
                    <div className="bg-muted/30 p-6 rounded-lg w-full max-w-md">
                        <div className="flex flex-col space-y-3">
                            {/* Total Cost - use FCY for passthrough */}
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total Cost ({overallDisplayCurrency})</span>
                                <span className="font-mono">
                                    {formatCurrency(
                                        isOverallPassthrough
                                            ? (totals.total_sell_fcy || '0')
                                            : totals.cost_pgk,
                                        overallDisplayCurrency
                                    )}
                                </span>
                            </div>
                            {/* Show AUD cost only if not passthrough */}
                            {!isOverallPassthrough && totals.cost_aud && (
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Total Cost (AUD)</span>
                                    <span className="font-mono">{formatCurrency(totals.cost_aud, 'AUD')}</span>
                                </div>
                            )}
                            {/* Total Sell (Ex GST) - use FCY for passthrough */}
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total Sell (Ex GST)</span>
                                <span className="font-mono">
                                    {formatCurrency(
                                        isOverallPassthrough
                                            ? (totals.total_sell_fcy || '0')
                                            : totals.sell_pgk,
                                        overallDisplayCurrency
                                    )}
                                </span>
                            </div>
                            {/* Total GST - use FCY for passthrough */}
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total GST</span>
                                <span className="font-mono">
                                    {formatCurrency(
                                        isOverallPassthrough
                                            ? '0'  // No GST for passthrough A2D DAP
                                            : totals.gst_amount,
                                        overallDisplayCurrency
                                    )}
                                </span>
                            </div>
                            <Separator className="my-2" />
                            <div className="flex justify-between items-end">
                                <span className="text-base font-semibold text-foreground">Total Quote Amount</span>
                                <div className="text-right">
                                    <span className="block text-3xl font-bold text-primary tracking-tight">
                                        {formatCurrency(
                                            sellCurrency === 'PGK'
                                                ? (totals.sell_pgk_incl_gst || totals.sell_pgk)
                                                : (totals.total_sell_fcy_incl_gst || totals.total_sell_fcy),
                                            sellCurrency
                                        )}
                                    </span>
                                    <span className="text-xs text-muted-foreground uppercase font-medium">{sellCurrency} (Inc GST)</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}

// ============================================================
// BUCKET SECTION - Collapsible bucket with subtotal
// ============================================================
function BucketSection({
    bucket,
    lines,
    sellCurrency
}: {
    bucket: BucketType;
    lines: SellLine[];
    sellCurrency: string;
}) {
    const [isExpanded, setIsExpanded] = useState(true);
    const config = BUCKET_CONFIG[bucket];
    const Icon = config.icon;

    // Check if this is a FCY passthrough bucket (e.g., A2D DAP PREPAID)
    const isPassthrough = isFCYPassthrough(lines);
    const displayCurrency = isPassthrough ? getLineCurrency(lines) : 'PGK';

    // Calculate bucket subtotal - use FCY or PGK based on passthrough status
    const bucketTotal = isPassthrough
        ? calculateBucketTotal(lines, 'sell_fcy_incl_gst')
        : calculateBucketTotal(lines, 'sell_pgk_incl_gst');
    const bucketSellExGst = isPassthrough
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    // Get subgroup config based on bucket
    const subgroupConfig = bucket === 'ORIGIN' ? ORIGIN_SUBGROUPS
        : bucket === 'FREIGHT' ? FREIGHT_SUBGROUPS
            : DESTINATION_SUBGROUPS;

    // Group lines by subgroup
    const grouped = lines.reduce((acc, line) => {
        const subgroupKey = getSubgroup(line.component, bucket);
        if (!acc[subgroupKey]) {
            acc[subgroupKey] = [];
        }
        acc[subgroupKey].push(line);
        return acc;
    }, {} as Record<string, SellLine[]>);

    // Sort subgroups by order
    const sortedSubgroups = Object.entries(grouped).sort((a, b) => {
        const orderA = subgroupConfig[a[0]]?.order || 999;
        const orderB = subgroupConfig[b[0]]?.order || 999;
        return orderA - orderB;
    });

    return (
        <div className={`rounded-lg border-2 ${config.colorClass.split(' ')[0]} shadow-sm overflow-hidden`}>
            {/* Bucket Header - Collapsible */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full ${config.bgClass} px-4 py-3 flex items-center justify-between hover:opacity-90 transition-opacity`}
            >
                <div className="flex items-center gap-3">
                    <Icon className={`w-5 h-5 ${config.colorClass.split(' ')[1]}`} />
                    <h3 className={`font-bold text-base uppercase tracking-wide ${config.colorClass.split(' ')[1]}`}>
                        {config.title}
                    </h3>
                    <Badge variant="outline" className={`text-xs font-normal ${config.badgeClass}`}>
                        {lines.length} items
                    </Badge>
                </div>
                <div className="flex items-center gap-4">
                    <div className="text-right">
                        <span className={`font-bold text-lg font-mono ${config.colorClass.split(' ')[1]}`}>
                            {formatCurrency(bucketTotal, displayCurrency)}
                        </span>
                    </div>
                    {isExpanded ? (
                        <ChevronDown className={`w-5 h-5 ${config.colorClass.split(' ')[1]}`} />
                    ) : (
                        <ChevronRight className={`w-5 h-5 ${config.colorClass.split(' ')[1]}`} />
                    )}
                </div>
            </button>

            {/* Bucket Content */}
            {isExpanded && (
                <div className="border-t">
                    {sortedSubgroups.map(([subgroupKey, subgroupLines], groupIndex) => (
                        <SubgroupSection
                            key={subgroupKey}
                            title={subgroupConfig[subgroupKey]?.title || 'Other Services'}
                            lines={subgroupLines}
                            sellCurrency={sellCurrency}
                            isFirst={groupIndex === 0}
                            bucketColor={config.colorClass.split(' ')[1]}
                        />
                    ))}

                    {/* Bucket Subtotal Row */}
                    <div className={`${config.bgClass} px-4 py-3 border-t flex justify-between items-center`}>
                        <span className={`font-semibold text-sm ${config.colorClass.split(' ')[1]}`}>
                            Bucket Subtotal
                        </span>
                        <div className="flex gap-6 text-sm">
                            <div className="text-right">
                                <span className="text-muted-foreground text-xs">Sell (Ex GST)</span>
                                <span className="block font-mono font-medium">{formatCurrency(bucketSellExGst, displayCurrency)}</span>
                            </div>
                            <div className="text-right">
                                <span className="text-muted-foreground text-xs">Total (Inc GST)</span>
                                <span className={`block font-mono font-bold ${config.colorClass.split(' ')[1]}`}>
                                    {formatCurrency(bucketTotal, displayCurrency)}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================
// SUBGROUP SECTION - Collapsible subgroup within bucket
// ============================================================
function SubgroupSection({
    title,
    lines,
    sellCurrency,
    isFirst,
    bucketColor
}: {
    title: string;
    lines: SellLine[];
    sellCurrency: string;
    isFirst: boolean;
    bucketColor: string;
}) {
    const [isExpanded, setIsExpanded] = useState(false); // Collapsed by default

    // Detect FCY passthrough for this subgroup
    const isPassthrough = isFCYPassthrough(lines);
    const displayCurrency = isPassthrough ? getLineCurrency(lines) : 'PGK';

    // Calculate subgroup total using correct currency
    const subgroupTotal = isPassthrough
        ? lines.reduce((sum, l) => sum + parseFloat(l.sell_fcy_incl_gst || l.sell_fcy || '0'), 0)
        : lines.reduce((sum, l) => sum + parseFloat(l.sell_pgk_incl_gst || l.sell_pgk || '0'), 0);

    return (
        <div className={!isFirst ? 'border-t' : ''}>
            {/* Subgroup Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full bg-muted/20 px-4 py-2 border-b border-muted/40 flex items-center justify-between hover:bg-muted/30 transition-colors"
            >
                <div className="flex items-center gap-2">
                    {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    ) : (
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    )}
                    <div className={`w-1 h-4 rounded-full ${bucketColor.replace('text-', 'bg-')}`}></div>
                    <span className="text-xs font-semibold text-foreground/70 uppercase tracking-wide">
                        {title}
                    </span>
                    <Badge variant="secondary" className="text-[10px] h-4 px-1.5 bg-background">
                        {lines.length}
                    </Badge>
                </div>
                <span className="text-xs font-mono text-muted-foreground">
                    {formatCurrency(subgroupTotal, displayCurrency)}
                </span>
            </button>

            {/* Subgroup Table */}
            {isExpanded && (
                <Table>
                    <TableHeader className="bg-muted/5">
                        <TableRow className="hover:bg-transparent border-b-muted/30">
                            <TableHead className="w-[35%] text-xs">Charge Details</TableHead>
                            <TableHead className="text-right w-[10%] text-muted-foreground font-normal text-xs">FX Rate</TableHead>
                            <TableHead className="text-right w-[12%] text-muted-foreground font-normal text-xs">Cost</TableHead>
                            <TableHead className="text-right w-[10%] text-muted-foreground font-normal text-xs">Margin</TableHead>
                            <TableHead className="text-right w-[12%] text-xs">Sell (Ex)</TableHead>
                            <TableHead className="text-right w-[10%] text-xs">GST</TableHead>
                            <TableHead className="text-right w-[11%] font-semibold text-foreground text-xs">Total</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {lines.map((line: SellLine, index: number) => (
                            <ChargeRow key={index} line={line} sellCurrency={sellCurrency} />
                        ))}
                    </TableBody>
                </Table>
            )}
        </div>
    );
}

// ============================================================
// CHARGE ROW - Individual charge line
// ============================================================
function ChargeRow({ line, sellCurrency }: { line: SellLine; sellCurrency: string }) {
    // Detect if this line is FCY passthrough (sell_currency is not PGK and has FCY values)
    const isPassthrough = line.sell_currency && line.sell_currency !== 'PGK' && parseFloat(line.sell_fcy || '0') > 0;
    const displayCurrency = isPassthrough ? line.sell_currency : 'PGK';

    // Choose correct values based on passthrough status
    const costValue = isPassthrough ? line.sell_fcy : line.cost_pgk;  // For passthrough, cost = sell (no margin)
    const sellExGstValue = isPassthrough ? line.sell_fcy : line.sell_pgk;

    return (
        <TableRow className="hover:bg-muted/10 transition-colors border-b-muted/20">
            {/* Charge Details Column */}
            <TableCell className="py-3">
                <div className="flex flex-col gap-1">
                    <span className="font-medium text-foreground text-sm">
                        {line.description}
                    </span>
                    <div className="flex items-center gap-2">
                        <Badge variant="secondary" className="text-[10px] px-1.5 h-5 font-normal text-muted-foreground bg-muted/60">
                            {line.component || 'MISC'}
                        </Badge>
                        {line.line_type !== 'COMPONENT' && (
                            <Badge variant="outline" className="text-[10px] px-1.5 h-5">
                                {line.line_type}
                            </Badge>
                        )}
                    </div>
                </div>
            </TableCell>

            {/* FX Rate */}
            <TableCell className="text-right font-mono text-xs text-muted-foreground/60">
                {parseFloat(line.exchange_rate) !== 1 ? line.exchange_rate : '-'}
            </TableCell>

            {/* Cost */}
            <TableCell className="text-right font-mono text-sm text-muted-foreground">
                {formatCurrency(costValue, displayCurrency)}
            </TableCell>

            {/* Margin */}
            <TableCell className="text-right font-mono text-xs">
                {parseFloat(line.margin_percent) > 0 ? (
                    <span className="text-emerald-600 font-medium bg-emerald-50 px-1.5 py-0.5 rounded">
                        {formatPercent(line.margin_percent)}
                    </span>
                ) : (
                    <span className="text-muted-foreground/30">-</span>
                )}
            </TableCell>

            {/* Sell Ex GST */}
            <TableCell className="text-right font-mono text-sm font-medium text-foreground/90">
                {formatCurrency(sellExGstValue, displayCurrency)}
            </TableCell>

            {/* GST */}
            <TableCell className="text-right font-mono text-sm text-muted-foreground">
                {parseFloat(line.gst_amount || '0') > 0 ? (
                    formatCurrency(line.gst_amount, displayCurrency)
                ) : (
                    <span className="text-muted-foreground/30">-</span>
                )}
            </TableCell>

            {/* Total Inc GST */}
            <TableCell className="text-right font-mono text-sm font-bold text-foreground bg-muted/5">
                {formatCurrency(
                    isPassthrough
                        ? (line.sell_fcy_incl_gst || line.sell_fcy)
                        : (line.sell_pgk_incl_gst || line.sell_pgk),
                    displayCurrency
                )}
            </TableCell>
        </TableRow>
    );
}
