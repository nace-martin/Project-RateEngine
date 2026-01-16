import { UnifiedQuote, formatDate, formatCurrency } from "@/lib/quote-helpers";
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";
import { Button } from "@/components/ui/button";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    SheetFooter,
} from "@/components/ui/sheet";
import { ArrowRight, Box, Calendar, MapPin, Scale, User, Plane, Ship, Truck } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";

interface QuoteQuickLookProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    quote: UnifiedQuote | null;
}

export function QuoteQuickLook({ open, onOpenChange, quote }: QuoteQuickLookProps) {
    if (!quote) return null;

    const getModeIcon = (mode: string) => {
        switch (mode?.toUpperCase()) {
            case 'SEA': return <Ship className="h-4 w-4" />;
            case 'ROAD': return <Truck className="h-4 w-4" />;
            default: return <Plane className="h-4 w-4" />;
        }
    };

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="w-full sm:max-w-md flex flex-col h-full bg-white sm:w-[540px] sm:max-w-[540px]">
                <SheetHeader className="pb-6 border-b">
                    <div className="flex items-center justify-between mb-2">
                        <Badge variant="outline" className="font-mono text-xs">{quote.mode}</Badge>
                        <span className="text-xs text-muted-foreground">Created {formatDate(quote.date)}</span>
                    </div>
                    <SheetTitle className="text-2xl font-bold flex items-center gap-3">
                        {quote.number}
                        <QuoteStatusBadge status={quote.rawStatus} size="sm" />
                    </SheetTitle>
                    <SheetDescription className="text-base flex items-center gap-2 mt-1">
                        <User className="h-4 w-4" /> {quote.customer}
                    </SheetDescription>
                </SheetHeader>

                <div className="flex-1 py-6 space-y-8 overflow-y-auto">
                    {/* Route Info */}
                    <div className="space-y-3">
                        <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                            <MapPin className="h-4 w-4" /> Route Details
                        </h4>
                        <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 flex items-center justify-between">
                            <div className="text-center flex-1">
                                <div className="text-sm text-slate-500 mb-1">Origin</div>
                                <div className="font-bold text-lg">{quote.route.split('→')[0].trim()}</div>
                            </div>
                            <ArrowRight className="h-5 w-5 text-slate-300 mx-2" />
                            <div className="text-center flex-1">
                                <div className="text-sm text-slate-500 mb-1">Destination</div>
                                <div className="font-bold text-lg">{quote.route.split('→')[1].trim()}</div>
                            </div>
                        </div>
                    </div>

                    {/* Cargo Info */}
                    <div className="space-y-3">
                        <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                            <Box className="h-4 w-4" /> Cargo Description
                        </h4>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <div className="text-xs text-slate-500">Total Weight</div>
                                <div className="font-semibold">{quote.weight}</div>
                            </div>
                            <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <div className="text-xs text-slate-500">Service Mode</div>
                                <div className="font-semibold flex items-center gap-1">
                                    {getModeIcon(quote.mode)}
                                    {quote.mode}
                                </div>
                            </div>
                            <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <div className="text-xs text-slate-500">Incoterms</div>
                                <div className="font-semibold">{quote.incoterms}</div>
                            </div>
                            <div className="bg-white p-3 rounded-lg border border-slate-200">
                                <div className="text-xs text-slate-500">Scope</div>
                                <div className="font-semibold">{quote.scope}</div>
                            </div>
                            <div className="col-span-2 bg-white p-3 rounded-lg border border-slate-200">
                                <div className="text-xs text-slate-500">Created By</div>
                                <div className="font-semibold truncate">{quote.createdBy}</div>
                            </div>
                        </div>
                    </div>

                    {/* Financials */}
                    <div className="space-y-3">
                        <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
                            <Scale className="h-4 w-4" /> Financial Summary
                        </h4>
                        <div className="p-5 rounded-xl bg-blue-50 border border-blue-100 space-y-3">
                            <div className="flex justify-between items-center text-sm text-blue-900/60">
                                <span>Subtotal</span>
                                <span>--</span>
                            </div>
                            <div className="h-px bg-blue-200/50" />
                            <div className="flex justify-between items-baseline pt-1">
                                <span className="font-medium text-blue-900">Total (Inc. GST)</span>
                                <span className="text-2xl font-bold text-blue-700">{quote.total}</span>
                            </div>
                        </div>
                    </div>
                </div>

                <SheetFooter className="pt-6 border-t mt-auto">
                    <Button className="w-full h-12 text-base shadow-lg shadow-blue-900/5" asChild>
                        <Link href={quote.actionLink}>
                            View Full Quote & Actions <ArrowRight className="ml-2 h-4 w-4" />
                        </Link>
                    </Button>
                </SheetFooter>
            </SheetContent>
        </Sheet>
    );
}
