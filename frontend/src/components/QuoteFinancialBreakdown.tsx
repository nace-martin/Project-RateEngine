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
import { Button } from "@/components/ui/button";
import { ChevronDown, ChevronRight, Package, Plane, MapPin, Eye, EyeOff } from "lucide-react";
import { usePermissions } from "@/hooks/usePermissions";

// ============================================================
// VIEW MODE TYPES
// ============================================================
type ViewMode = 'CLIENT' | 'INTERNAL';

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
        icon: Plane, // ✈️ icon instead of colour dominance
        colorClass: 'border-blue-500 text-blue-700', // Aligned with Origin (no purple)
        bgClass: 'bg-blue-50/70', // Slightly different shade for distinction
        badgeClass: 'bg-blue-100 text-blue-700 border-blue-200',
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
    'collection': {
        title: 'Collection Services',
        order: 1,
        codes: ['PICKUP', 'PICKUP_FUEL', 'PICKUP_EXP', 'PICKUP_FUEL_ORG', 'FUEL_SURCHARGE_EXP', 'STORAGE_EXP']
    },
    'documentation': {
        title: 'Documentation',
        order: 2,
        codes: ['DOC_EXP', 'AWB_FEE', 'DOC_EXP_AWB', 'DOC_EXP_BIC', 'DOC_EXP_LCC', 'AWB_FEE_SELL', 'DOC_EXP_SELL']
    },
    'customs': {
        title: 'Customs & Brokerage',
        order: 3,
        codes: ['CLEAR_EXP', 'CUS_ENTRY_EXP', 'CLEARANCE_SELL', 'AGENCY_EXP', 'AGENCY_EXP_SELL']
    },
    'terminal': {
        title: 'Terminal & Handling',
        order: 4,
        codes: ['HND_EXP_BSC', 'HND_EXP_VA', 'SEC_EXP_MXC', 'HND_EXP_BPC', 'HND_EXP_RAC']
    },
    'inspection': {
        title: 'Inspection & Security',
        order: 5,
        codes: ['XRAY', 'CTO', 'FUMIGATION']
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
    const { canViewCOGS, canViewMargins } = usePermissions();
    const { sell_lines, totals, exchange_rates } = result;
    const sellCurrency = totals.currency;

    // RBAC: Only users who can view COGS can see Internal view
    const canViewInternal = canViewCOGS;
    const [viewMode, setViewMode] = useState<ViewMode>(canViewInternal ? 'INTERNAL' : 'CLIENT');

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
                            {viewMode === 'CLIENT' ? 'Client View' : 'Internal View'} (Computed: {result.computation_date})
                        </CardDescription>
                    </div>
                    <div className="flex items-center gap-3">
                        {/* View Mode Toggle - Only show if user can access Internal */}
                        {canViewInternal && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => setViewMode(viewMode === 'CLIENT' ? 'INTERNAL' : 'CLIENT')}
                                className="gap-2"
                            >
                                {viewMode === 'CLIENT' ? (
                                    <><Eye className="h-4 w-4" /> Internal View</>
                                ) : (
                                    <><EyeOff className="h-4 w-4" /> Client View</>
                                )}
                            </Button>
                        )}
                        {/* FX Rates - Only show in Internal view */}
                        {viewMode === 'INTERNAL' && Object.entries(exchange_rates).map(([pair, rate]) => (
                            <Badge key={pair} variant="outline" className="text-xs font-mono">
                                {pair}: {rate}
                            </Badge>
                        ))}
                    </div>
                </div>
            </CardHeader>
            <CardContent className="p-8 space-y-8">
                {/* ORIGIN BUCKET */}
                {buckets.ORIGIN.length > 0 && (
                    <BucketSection
                        bucket="ORIGIN"
                        lines={buckets.ORIGIN}
                        sellCurrency={sellCurrency}
                        viewMode={viewMode}
                    />
                )}

                {/* FREIGHT BUCKET */}
                {buckets.FREIGHT.length > 0 && (
                    <BucketSection
                        bucket="FREIGHT"
                        lines={buckets.FREIGHT}
                        sellCurrency={sellCurrency}
                        viewMode={viewMode}
                    />
                )}

                {/* DESTINATION BUCKET */}
                {buckets.DESTINATION.length > 0 && (
                    <BucketSection
                        bucket="DESTINATION"
                        lines={buckets.DESTINATION}
                        sellCurrency={sellCurrency}
                        viewMode={viewMode}
                    />
                )}

                {/* QUOTE SUMMARY - Client-friendly, no cost/margin */}
                <div className="flex justify-end mt-6">
                    <div className="bg-muted/30 p-6 rounded-lg w-full max-w-md">
                        <div className="flex flex-col space-y-3">
                            {/* Total Cost - Only show in Internal view */}
                            {viewMode === 'INTERNAL' && (
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
                            )}
                            {/* Show AUD cost only in Internal view and if not passthrough */}
                            {viewMode === 'INTERNAL' && !isOverallPassthrough && totals.cost_aud && (
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
    sellCurrency,
    viewMode
}: {
    bucket: BucketType;
    lines: SellLine[];
    sellCurrency: string;
    viewMode: ViewMode;
}) {
    const [isExpanded, setIsExpanded] = useState(true);
    const config = BUCKET_CONFIG[bucket];
    const Icon = config.icon;

    // Use the quote's output currency to determine display
    // If output currency is NOT PGK, show amounts in FCY
    const displayInFCY = sellCurrency !== 'PGK';
    const displayCurrency = displayInFCY ? sellCurrency : 'PGK';

    // Calculate bucket subtotal - use FCY or PGK based on output currency
    const bucketTotal = displayInFCY
        ? calculateBucketTotal(lines, 'sell_fcy_incl_gst')
        : calculateBucketTotal(lines, 'sell_pgk_incl_gst');
    const bucketSellExGst = displayInFCY
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
        <div className={`rounded-lg border ${config.colorClass.split(' ')[0]} shadow-sm overflow-hidden`}>
            {/* Bucket Header - Collapsible */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full ${config.bgClass} px-5 py-4 flex items-center justify-between hover:opacity-90 transition-opacity`}
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

            {/* Bucket Content - No border-t to reduce stacking */}
            {isExpanded && (
                <div className="bg-white">
                    {/* Subgroups with spacing between them */}
                    <div className="divide-y divide-muted/20">
                        {sortedSubgroups.map(([subgroupKey, subgroupLines]) => (
                            <SubgroupSection
                                key={subgroupKey}
                                title={subgroupConfig[subgroupKey]?.title || 'Other Services'}
                                lines={subgroupLines}
                                sellCurrency={sellCurrency}
                                bucketColor={config.colorClass.split(' ')[1]}
                                viewMode={viewMode}
                            />
                        ))}
                    </div>

                    {/* Bucket Subtotal Row - Clean separation */}
                    <div className={`${config.bgClass} px-5 py-4 mt-2 flex justify-between items-center`}>
                        <span className={`font-semibold text-sm ${config.colorClass.split(' ')[1]}`}>
                            Bucket Subtotal
                        </span>
                        <div className="flex gap-8 text-sm">
                            <div className="text-right">
                                <span className="text-muted-foreground text-xs block mb-0.5">Sell (Ex GST)</span>
                                <span className="font-mono font-medium">{formatCurrency(bucketSellExGst, displayCurrency)}</span>
                            </div>
                            <div className="text-right">
                                <span className="text-muted-foreground text-xs block mb-0.5">Total (Inc GST)</span>
                                <span className={`font-mono font-bold ${config.colorClass.split(' ')[1]}`}>
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
    bucketColor,
    viewMode
}: {
    title: string;
    lines: SellLine[];
    sellCurrency: string;
    bucketColor: string;
    viewMode: ViewMode;
}) {
    const [isExpanded, setIsExpanded] = useState(false); // Collapsed by default

    // Use the quote's output currency to determine display
    const displayInFCY = sellCurrency !== 'PGK';
    const displayCurrency = displayInFCY ? sellCurrency : 'PGK';

    // Calculate subgroup total using correct currency
    const subgroupTotal = displayInFCY
        ? lines.reduce((sum, l) => sum + parseFloat(l.sell_fcy_incl_gst || l.sell_fcy || '0'), 0)
        : lines.reduce((sum, l) => sum + parseFloat(l.sell_pgk_incl_gst || l.sell_pgk || '0'), 0);

    return (
        <div>
            {/* Subgroup Header - No bottom border, uses spacing */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full bg-muted/10 px-5 py-3 flex items-center justify-between hover:bg-muted/20 transition-colors"
            >
                <div className="flex items-center gap-3">
                    {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-muted-foreground" />
                    ) : (
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    )}
                    <div className={`w-1 h-4 rounded-full ${bucketColor.replace('text-', 'bg-')}`}></div>
                    <span className="text-sm font-medium text-foreground/80">
                        {title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                        ({lines.length})
                    </span>
                </div>
                <span className="text-sm font-mono font-medium text-foreground">
                    {formatCurrency(subgroupTotal, displayCurrency)}
                </span>
            </button>

            {/* Subgroup Table - With padding, no outer border */}
            {isExpanded && (
                <div className="px-5 pb-4 pt-2">
                    <Table>
                        <TableHeader>
                            <TableRow className="hover:bg-transparent border-b border-muted/30">
                                <TableHead className={viewMode === 'CLIENT' ? 'w-[45%] text-xs font-medium' : 'w-[35%] text-xs font-medium'}>Description</TableHead>
                                {viewMode === 'INTERNAL' && (
                                    <TableHead className="text-right w-[10%] text-muted-foreground font-normal text-xs">FX Rate</TableHead>
                                )}
                                {viewMode === 'INTERNAL' && (
                                    <TableHead className="text-right w-[12%] text-muted-foreground font-normal text-xs">Cost</TableHead>
                                )}
                                {viewMode === 'INTERNAL' && (
                                    <TableHead className="text-right w-[10%] text-muted-foreground font-normal text-xs">Margin</TableHead>
                                )}
                                <TableHead className="text-right w-[15%] text-xs font-medium">Sell (Ex GST)</TableHead>
                                <TableHead className="text-right w-[12%] text-xs font-medium">GST</TableHead>
                                <TableHead className="text-right w-[15%] font-semibold text-foreground text-xs">Total</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {lines.map((line: SellLine, index: number) => (
                                <ChargeRow key={index} line={line} sellCurrency={sellCurrency} viewMode={viewMode} isLast={index === lines.length - 1} />
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </div>
    );
}

// ============================================================
// CHARGE ROW - Individual charge line
// ============================================================
function ChargeRow({ line, sellCurrency, viewMode, isLast }: { line: SellLine; sellCurrency: string; viewMode: ViewMode; isLast?: boolean }) {
    // Use the quote's output currency to determine display
    const displayInFCY = sellCurrency !== 'PGK';
    const displayCurrency = displayInFCY ? sellCurrency : 'PGK';

    // Choose correct values based on output currency
    const costValue = displayInFCY ? line.sell_fcy : line.cost_pgk;  // For FCY quotes, cost in FCY
    const sellExGstValue = displayInFCY ? line.sell_fcy : line.sell_pgk;

    return (
        <TableRow className={`hover:bg-muted/5 transition-colors ${!isLast ? 'border-b border-muted/15' : ''}`}>
            {/* Charge Details Column */}
            <TableCell className="py-4">
                <div className="flex flex-col gap-0.5">
                    <span className="font-medium text-foreground text-sm">
                        {line.description}
                    </span>
                    <span className="text-xs text-muted-foreground">
                        {line.component || 'MISC'}
                    </span>
                </div>
            </TableCell>

            {/* FX Rate - Internal only */}
            {viewMode === 'INTERNAL' && (
                <TableCell className="text-right font-mono text-xs text-muted-foreground py-4">
                    {parseFloat(line.exchange_rate) !== 1 ? line.exchange_rate : '-'}
                </TableCell>
            )}

            {/* Cost - Internal only */}
            {viewMode === 'INTERNAL' && (
                <TableCell className="text-right font-mono text-sm text-muted-foreground py-4">
                    {formatCurrency(costValue, displayCurrency)}
                </TableCell>
            )}

            {/* Margin - Internal only */}
            {viewMode === 'INTERNAL' && (
                <TableCell className="text-right font-mono text-xs py-4">
                    {parseFloat(line.margin_percent) > 0 ? (
                        <span className="text-emerald-600 font-medium">
                            {formatPercent(line.margin_percent)}
                        </span>
                    ) : (
                        <span className="text-muted-foreground/40">-</span>
                    )}
                </TableCell>
            )}

            {/* Sell Ex GST - Always visible */}
            <TableCell className="text-right font-mono text-sm font-medium text-foreground/90 py-4">
                {formatCurrency(sellExGstValue, displayCurrency)}
            </TableCell>

            {/* GST - Always visible */}
            <TableCell className="text-right font-mono text-sm text-muted-foreground py-4">
                {parseFloat(line.gst_amount || '0') > 0 ? (
                    formatCurrency(line.gst_amount, displayCurrency)
                ) : (
                    <span className="text-muted-foreground/40">-</span>
                )}
            </TableCell>

            {/* Total Inc GST - Always visible */}
            <TableCell className="text-right font-mono text-sm font-bold text-foreground py-4">
                {formatCurrency(
                    displayInFCY
                        ? (line.sell_fcy_incl_gst || line.sell_fcy)
                        : (line.sell_pgk_incl_gst || line.sell_pgk),
                    displayCurrency
                )}
            </TableCell>
        </TableRow>
    );
}
