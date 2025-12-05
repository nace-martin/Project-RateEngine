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

// Charge subgrouping definitions
interface ChargeSubgroup {
    title: string;
    order: number;
    codes: string[];
}

const CHARGE_SUBGROUPS: Record<string, ChargeSubgroup> = {
    // Origin subgroups
    'origin_documentation': {
        title: 'Documentation & Compliance',
        order: 1,
        codes: ['DOC_EXP', 'AGENCY_EXP', 'AWB_FEE']
    },
    'origin_inspection': {
        title: 'Inspection & Security',
        order: 2,
        codes: ['XRAY', 'CTO']
    },
    'origin_collection': {
        title: 'Collection Services',
        order: 3,
        codes: ['PICKUP', 'PICKUP_FUEL']
    },

    // Destination subgroups
    'destination_customs': {
        title: 'Customs & Regulatory',
        order: 1,
        codes: ['CLEARANCE', 'AGENCY_IMP']
    },
    'destination_handling': {
        title: 'Terminal & Handling',
        order: 2,
        codes: ['DOC_IMP', 'HANDLING', 'TERM_INT', 'CTO']
    },
    'destination_delivery': {
        title: 'Delivery Services',
        order: 3,
        codes: ['CARTAGE', 'CARTAGE_FUEL']
    },

    // Freight (usually just one group)
    'freight_transport': {
        title: 'International Transport',
        order: 1,
        codes: ['FRT_AIR', 'FRT_SEA', 'FRT_ROAD']
    }
};

function getSubgroup(component: string | null | undefined, leg: string): string {
    if (!component) return 'other';

    const legPrefix = leg.toLowerCase().replace('main', 'freight');
    for (const [key, config] of Object.entries(CHARGE_SUBGROUPS)) {
        if (key.startsWith(legPrefix) && config.codes.includes(component)) {
            return key;
        }
    }
    return 'other';
}

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
                {/* Origin Charges */}
                {sell_lines.filter((l: SellLine) => l.leg === 'ORIGIN').length > 0 && (
                    <ChargeSection
                        title="Origin Charges"
                        lines={sell_lines.filter((l: SellLine) => l.leg === 'ORIGIN')}
                        sellCurrency={sellCurrency}
                    />
                )}

                {/* Main/Freight Charges */}
                {sell_lines.filter((l: SellLine) => l.leg === 'MAIN').length > 0 && (
                    <ChargeSection
                        title="Freight Charges"
                        lines={sell_lines.filter((l: SellLine) => l.leg === 'MAIN')}
                        sellCurrency={sellCurrency}
                    />
                )}

                {/* Destination Charges */}
                {sell_lines.filter((l: SellLine) => l.leg === 'DESTINATION').length > 0 && (
                    <ChargeSection
                        title="Destination Charges - Clearance and Delivery"
                        lines={sell_lines.filter((l: SellLine) => l.leg === 'DESTINATION')}
                        sellCurrency={sellCurrency}
                    />
                )}

                {/* Other Charges (catch-all) */}
                {sell_lines.filter((l: SellLine) => !['ORIGIN', 'MAIN', 'DESTINATION'].includes(l.leg || '')).length > 0 && (
                    <ChargeSection
                        title="Additional Services"
                        lines={sell_lines.filter((l: SellLine) => !['ORIGIN', 'MAIN', 'DESTINATION'].includes(l.leg || ''))}
                        sellCurrency={sellCurrency}
                    />
                )}

                <div className="flex justify-end mt-6">
                    <div className="bg-muted/30 p-6 rounded-lg w-full max-w-md">
                        <div className="flex flex-col space-y-3">
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total Cost (PGK)</span>
                                <span className="font-mono">{formatCurrency(totals.cost_pgk, 'PGK')}</span>
                            </div>
                            {totals.cost_aud && (
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Total Cost (AUD)</span>
                                    <span className="font-mono">{formatCurrency(totals.cost_aud, 'AUD')}</span>
                                </div>
                            )}
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total Sell (Ex GST)</span>
                                <span className="font-mono">{formatCurrency(totals.sell_pgk, 'PGK')}</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-muted-foreground">Total GST</span>
                                <span className="font-mono">{formatCurrency(totals.gst_amount, 'PGK')}</span>
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

function ChargeSection({ title, lines, sellCurrency }: { title: string, lines: SellLine[], sellCurrency: string }) {
    if (lines.length === 0) return null;

    // Group lines by subgroup
    const grouped = lines.reduce((acc, line) => {
        const subgroupKey = getSubgroup(line.component, line.leg || '');
        if (!acc[subgroupKey]) {
            acc[subgroupKey] = [];
        }
        acc[subgroupKey].push(line);
        return acc;
    }, {} as Record<string, SellLine[]>);

    // Sort subgroups by order
    const sortedSubgroups = Object.entries(grouped).sort((a, b) => {
        const orderA = CHARGE_SUBGROUPS[a[0]]?.order || 999;
        const orderB = CHARGE_SUBGROUPS[b[0]]?.order || 999;
        return orderA - orderB;
    });

    return (
        <div className="rounded-lg border shadow-sm overflow-hidden mb-8">
            <div className="bg-muted/40 px-4 py-3 border-b flex items-center justify-between">
                <h3 className="font-semibold text-sm uppercase tracking-wider text-foreground/80">{title}</h3>
                <Badge variant="outline" className="text-xs font-normal text-muted-foreground">
                    {lines.length} items
                </Badge>
            </div>

            {sortedSubgroups.map(([subgroupKey, subgroupLines], groupIndex) => (
                <div key={subgroupKey} className={groupIndex > 0 ? 'border-t' : ''}>
                    {/* Subgroup Header */}
                    <div className="bg-muted/20 px-4 py-2 border-b border-muted/40">
                        <div className="flex items-center gap-2">
                            <div className="w-1 h-4 bg-primary/60 rounded-full"></div>
                            <span className="text-xs font-semibold text-foreground/70 uppercase tracking-wide">
                                {CHARGE_SUBGROUPS[subgroupKey]?.title || 'Additional Services'}
                            </span>
                            <Badge variant="secondary" className="text-[10px] h-4 px-1.5 bg-background">
                                {subgroupLines.length}
                            </Badge>
                        </div>
                    </div>

                    {/* Subgroup Table */}
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
                            {subgroupLines.map((line: SellLine, index: number) => (
                                <TableRow key={index} className="hover:bg-muted/10 transition-colors border-b-muted/20">
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
                                        {formatCurrency(line.cost_pgk, 'PGK')}
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
                                        {formatCurrency(line.sell_pgk, 'PGK')}
                                    </TableCell>

                                    {/* GST */}
                                    <TableCell className="text-right font-mono text-sm text-muted-foreground">
                                        {parseFloat(line.gst_amount || '0') > 0 ? (
                                            formatCurrency(line.gst_amount, 'PGK')
                                        ) : (
                                            <span className="text-muted-foreground/30">-</span>
                                        )}
                                    </TableCell>

                                    {/* Total Inc GST */}
                                    <TableCell className="text-right font-mono text-sm font-bold text-foreground bg-muted/5">
                                        {formatCurrency(
                                            line.sell_currency === 'PGK'
                                                ? (line.sell_pgk_incl_gst || line.sell_pgk)
                                                : (line.sell_fcy_incl_gst || line.sell_fcy),
                                            line.sell_currency
                                        )}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            ))}
        </div>
    );
}
