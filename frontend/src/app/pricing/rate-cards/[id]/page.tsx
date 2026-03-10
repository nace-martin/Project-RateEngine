'use client';

import React, { useCallback, useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getRateCardV3, RateCard, RateLine } from '@/lib/api';
import { Button } from '@/components/ui/button';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { RateLineDialog } from '@/components/pricing/RateLineDialog';
import { ImportRatesDialog } from '@/components/pricing/ImportRatesDialog';
import { Upload, Edit, Plus, ChevronRight, Trash2, Calendar, Globe, Truck, DollarSign, Layers, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

// Helper to determine rate card status
function getRateCardStatus(validFrom: string | null, validUntil: string | null): 'active' | 'draft' | 'expired' {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (!validFrom) return 'draft';

    const fromDate = new Date(validFrom);
    fromDate.setHours(0, 0, 0, 0);

    if (fromDate > today) return 'draft';

    if (validUntil) {
        const untilDate = new Date(validUntil);
        untilDate.setHours(0, 0, 0, 0);
        if (untilDate < today) return 'expired';
    }

    return 'active';
}

// Premium Status badge component
function StatusBadge({ status }: { status: 'active' | 'draft' | 'expired' }) {
    const config = {
        active: {
            label: 'Active',
            className: 'bg-gradient-to-r from-emerald-500 to-emerald-600 text-white border-0 shadow-sm shadow-emerald-200',
            dot: 'bg-white animate-pulse'
        },
        draft: {
            label: 'Draft',
            className: 'bg-gradient-to-r from-amber-400 to-amber-500 text-white border-0 shadow-sm shadow-amber-200',
            dot: 'bg-white'
        },
        expired: {
            label: 'Expired',
            className: 'bg-gray-100 text-gray-500 border border-gray-200',
            dot: 'bg-gray-400'
        },
    };

    const { label, className, dot } = config[status];
    return (
        <Badge className={`${className} px-3 py-1 text-xs font-medium`}>
            <span className={`w-1.5 h-1.5 rounded-full ${dot} mr-2`} />
            {label}
        </Badge>
    );
}

// Premium Weight Break Rate Grid
function WeightBreakGrid({ breaks }: { breaks: { id: string; from_value: number; to_value: number | null; rate: number }[] }) {
    if (!breaks || breaks.length === 0) {
        return <span className="text-muted-foreground">—</span>;
    }

    const sortedBreaks = [...breaks].sort((a, b) => a.from_value - b.from_value);

    return (
        <div className="inline-flex items-stretch rounded-lg overflow-hidden border border-slate-200 bg-gradient-to-b from-white to-slate-50 shadow-sm">
            {sortedBreaks.map((b, idx) => {
                const stepLabel = idx === 0 ? 'M' : `+${b.from_value}`;
                const isFirst = idx === 0;

                return (
                    <div
                        key={b.id}
                        className={`
                            flex flex-col items-center justify-center px-4 py-2 min-w-[60px]
                            ${!isFirst ? 'border-l border-slate-200' : ''}
                            ${isFirst ? 'bg-slate-800 text-white' : 'hover:bg-slate-100 transition-colors'}
                        `}
                    >
                        <span className={`text-[10px] font-bold uppercase tracking-wider mb-0.5 ${isFirst ? 'text-slate-300' : 'text-slate-400'}`}>
                            {stepLabel}
                        </span>
                        <span
                            className={`font-mono text-sm font-bold tabular-nums ${isFirst ? 'text-white' : 'text-slate-700'}`}
                            style={{ fontFeatureSettings: '"tnum"' }}
                        >
                            {Number(b.rate).toFixed(2)}
                        </span>
                    </div>
                );
            })}
        </div>
    );
}

// Helper to format rate display based on method
function formatRateDisplay(
    line: RateLine,
    currency: string,
    resolveComponent: (id: string | null) => string
): React.ReactNode {
    const method = line.method;

    if (method === 'WEIGHT_BREAK') {
        return <WeightBreakGrid breaks={line.breaks} />;
    }

    if (method === 'PERCENT') {
        const percent = Number(line.percent_value) * 100;
        const componentCode = resolveComponent(line.percent_of_component);
        return (
            <div className="flex items-center gap-2">
                <span className="inline-flex items-center justify-center w-12 h-8 rounded-md bg-gradient-to-br from-violet-500 to-purple-600 text-white font-mono font-bold text-sm shadow-sm">
                    {percent.toFixed(0)}%
                </span>
                <span className="text-slate-400 text-sm">of</span>
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-slate-800 text-white font-mono text-xs font-bold shadow-sm">
                    {componentCode}
                </span>
            </div>
        );
    }

    // FLAT or PER_UNIT
    if (line.breaks && line.breaks.length > 0) {
        const rate = Number(line.breaks[0].rate);
        return (
            <div className="flex items-baseline gap-1">
                <span
                    className="font-mono text-base font-bold text-slate-800 tabular-nums"
                    style={{ fontFeatureSettings: '"tnum"' }}
                >
                    {rate.toFixed(4)}
                </span>
                {line.unit && (
                    <span className="text-slate-400 text-xs font-medium">/{line.unit}</span>
                )}
            </div>
        );
    }

    return <span className="text-muted-foreground">—</span>;
}

// Method badge with premium styling
function MethodBadge({ method, unit }: { method: string; unit?: string | null }) {
    const methodConfig: Record<string, { bg: string; text: string; border: string }> = {
        'WEIGHT_BREAK': { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
        'PER_UNIT': { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
        'PERCENT': { bg: 'bg-violet-50', text: 'text-violet-700', border: 'border-violet-200' },
        'FLAT': { bg: 'bg-slate-50', text: 'text-slate-700', border: 'border-slate-200' },
    };

    const config = methodConfig[method] || methodConfig['FLAT'];

    return (
        <div className="flex items-center gap-1.5">
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${config.bg} ${config.text} ${config.border}`}>
                {method.replace('_', ' ')}
            </span>
            {unit && method !== 'FLAT' && (
                <span className="text-slate-400 text-xs">/{unit}</span>
            )}
        </div>
    );
}

// Info item for sidebar
function InfoItem({ icon: Icon, label, value, mono = false }: { icon: React.ElementType; label: string; value: string; mono?: boolean }) {
    return (
        <div className="flex items-start gap-3 py-2">
            <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center">
                <Icon className="w-4 h-4 text-slate-500" />
            </div>
            <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</div>
                <div className={`text-sm font-semibold text-slate-700 truncate ${mono ? 'font-mono' : ''}`}>{value}</div>
            </div>
        </div>
    );
}

export default function RateCardDetailPage() {
    const params = useParams();
    const id = params.id as string;
    const [rateCard, setRateCard] = useState<RateCard | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Dialog State
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [selectedLine, setSelectedLine] = useState<RateLine | null>(null);
    const [isImportOpen, setIsImportOpen] = useState(false);

    // Build a component lookup map for resolving UUIDs to codes
    const componentLookup = useMemo(() => {
        const map = new Map<string, string>();
        if (rateCard?.lines) {
            for (const line of rateCard.lines) {
                if (line.component) {
                    map.set(line.component, line.component_code || line.component);
                }
                if (line.component_code) {
                    map.set(line.component_code, line.component_code);
                }
            }
        }
        return map;
    }, [rateCard?.lines]);

    // Resolve component ID to human-readable code
    const resolveComponentCode = useCallback((componentId: string | null): string => {
        if (!componentId) return '—';
        return componentLookup.get(componentId) || componentId;
    }, [componentLookup]);

    const fetchCard = useCallback(async () => {
        try {
            setLoading(true);
            const data = await getRateCardV3(id);
            setRateCard(data);
        } catch (err) {
            setError('Failed to load rate card details.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchCard();
    }, [fetchCard]);

    const handleAddLine = () => {
        setSelectedLine(null);
        setIsDialogOpen(true);
    };

    const handleEditLine = (line: RateLine) => {
        setSelectedLine(line);
        setIsDialogOpen(true);
    };

    const handleDeleteLine = async (_line: RateLine) => {
        void _line;
        // Delete endpoint is not wired in this screen yet.
        return;
    };

    const handleSaveLine = () => {
        fetchCard();
    };

    const getYear = () => {
        if (rateCard?.valid_from) {
            return new Date(rateCard.valid_from).getFullYear().toString();
        }
        const yearMatch = rateCard?.name?.match(/\b(20\d{2})\b/);
        return yearMatch ? yearMatch[1] : 'Current';
    };

    if (loading && !rateCard) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50">
                <div className="container mx-auto py-8">
                    <div className="animate-pulse space-y-6">
                        <div className="h-8 w-80 bg-slate-200 rounded-lg" />
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            <div className="lg:col-span-2 h-96 bg-slate-100 rounded-2xl" />
                            <div className="space-y-4">
                                <div className="h-48 bg-slate-100 rounded-2xl" />
                                <div className="h-32 bg-slate-100 rounded-2xl" />
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (error || !rateCard) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-slate-50 flex items-center justify-center">
                <div className="bg-red-50 border border-red-200 text-red-700 px-6 py-4 rounded-xl shadow-sm">
                    <p className="font-medium">{error || 'Rate card not found'}</p>
                </div>
            </div>
        );
    }

    const status = getRateCardStatus(rateCard.valid_from, rateCard.valid_until);
    const lineCount = rateCard.lines?.length || 0;

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-blue-50/30">
            <div className="container mx-auto py-8 space-y-6">
                {/* Premium Header */}
                <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                    <div className="space-y-2">
                        {/* Breadcrumb Navigation */}
                        <nav className="flex items-center text-sm">
                            <Link
                                href="/pricing/rate-cards"
                                className="text-slate-500 hover:text-slate-800 transition-colors font-medium"
                            >
                                Rate Cards
                            </Link>
                            <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
                            <span className="text-slate-700 font-semibold">
                                {rateCard.supplier_name || 'Supplier'}
                            </span>
                            <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />
                            <span className="text-slate-700 font-semibold">
                                {getYear()}
                            </span>
                        </nav>
                        <div className="flex items-center gap-4">
                            <h1 className="text-3xl font-bold text-slate-900 tracking-tight">{rateCard.name}</h1>
                            <StatusBadge status={status} />
                        </div>
                        <p className="text-slate-500 text-sm">
                            {lineCount} rate line{lineCount !== 1 ? 's' : ''} • Last updated recently
                        </p>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setIsImportOpen(true)}
                            className="text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                        >
                            <Upload className="w-4 h-4 mr-2" />
                            Import
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            className="border-slate-200 text-slate-700 hover:bg-slate-50"
                        >
                            <Edit className="w-4 h-4 mr-2" />
                            Edit
                        </Button>
                        <Button
                            size="sm"
                            onClick={handleAddLine}
                            className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-lg shadow-blue-500/25"
                        >
                            <Plus className="w-4 h-4 mr-2" />
                            Add Line
                        </Button>
                    </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Rate Lines Table - Premium Card */}
                    <div className="lg:col-span-2">
                        <div className="bg-white rounded-2xl shadow-sm shadow-slate-200/50 border border-slate-200/60 overflow-hidden">
                            <div className="px-6 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
                                <h2 className="text-lg font-bold text-slate-800">Rate Lines</h2>
                                <p className="text-sm text-slate-500 mt-0.5">Configure pricing rules and weight breaks</p>
                            </div>
                            <div className="overflow-x-auto">
                                <Table>
                                    <TableHeader>
                                        <TableRow className="bg-slate-50/80 border-b border-slate-100">
                                            <TableHead className="font-bold text-slate-600 text-xs uppercase tracking-wider py-4">Component</TableHead>
                                            <TableHead className="font-bold text-slate-600 text-xs uppercase tracking-wider py-4">Method</TableHead>
                                            <TableHead className="font-bold text-slate-600 text-xs uppercase tracking-wider py-4 text-right w-32">Min Charge</TableHead>
                                            <TableHead className="font-bold text-slate-600 text-xs uppercase tracking-wider py-4">Rate</TableHead>
                                            <TableHead className="w-24 py-4"></TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {rateCard.lines?.map((line) => (
                                            <TableRow
                                                key={line.id}
                                                className="group hover:bg-blue-50/50 transition-all duration-150 border-b border-slate-100 last:border-0"
                                            >
                                                <TableCell className="py-4 align-top">
                                                    <div className="font-mono text-sm font-bold text-slate-800">{line.component_code}</div>
                                                    {line.description && (
                                                        <div className="text-xs text-slate-400 mt-1 max-w-[200px] truncate">{line.description}</div>
                                                    )}
                                                </TableCell>
                                                <TableCell className="py-4 align-top">
                                                    <MethodBadge method={line.method} unit={line.unit} />
                                                </TableCell>
                                                <TableCell
                                                    className="py-4 text-right align-top"
                                                    style={{ fontFeatureSettings: '"tnum"' }}
                                                >
                                                    {Number(line.min_charge) > 0 ? (
                                                        <div className="inline-flex items-baseline gap-1">
                                                            <span className="text-slate-400 text-xs font-medium">{rateCard.currency}</span>
                                                            <span className="font-mono text-sm font-bold text-slate-800 tabular-nums">
                                                                {Number(line.min_charge).toFixed(2)}
                                                            </span>
                                                        </div>
                                                    ) : (
                                                        <span className="text-slate-300">—</span>
                                                    )}
                                                </TableCell>
                                                <TableCell className="py-4 align-top">
                                                    {formatRateDisplay(line, rateCard.currency, resolveComponentCode)}
                                                </TableCell>
                                                <TableCell className="py-4 align-top">
                                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all duration-150">
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8 rounded-lg hover:bg-blue-100 hover:text-blue-600"
                                                            onClick={() => handleEditLine(line)}
                                                        >
                                                            <Edit className="w-4 h-4" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="h-8 w-8 rounded-lg hover:bg-red-100 hover:text-red-600"
                                                            onClick={() => handleDeleteLine(line)}
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </Button>
                                                    </div>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                        {!rateCard.lines?.length && (
                                            <TableRow>
                                                <TableCell colSpan={5} className="text-center py-16">
                                                    <div className="flex flex-col items-center gap-3">
                                                        <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center">
                                                            <Layers className="w-6 h-6 text-slate-400" />
                                                        </div>
                                                        <p className="text-slate-500 font-medium">No rate lines yet</p>
                                                        <Button size="sm" variant="outline" onClick={handleAddLine}>
                                                            <Plus className="w-4 h-4 mr-2" />
                                                            Add your first line
                                                        </Button>
                                                    </div>
                                                </TableCell>
                                            </TableRow>
                                        )}
                                    </TableBody>
                                </Table>
                            </div>
                        </div>
                    </div>

                    {/* Sidebar - Premium Cards */}
                    <div className="space-y-4">
                        {/* Configuration Card */}
                        <div className="bg-white rounded-2xl shadow-sm shadow-slate-200/50 border border-slate-200/60 overflow-hidden">
                            <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide">Configuration</h3>
                            </div>
                            <div className="p-5 space-y-1">
                                <InfoItem icon={Truck} label="Supplier" value={rateCard.supplier_name || '—'} />
                                <InfoItem icon={Globe} label="Mode" value={rateCard.mode || '—'} />
                                <InfoItem icon={DollarSign} label="Currency" value={rateCard.currency || '—'} mono />
                                <InfoItem icon={Layers} label="Scope" value={rateCard.scope || '—'} />
                            </div>
                        </div>

                        {/* Validity Card */}
                        <div className="bg-white rounded-2xl shadow-sm shadow-slate-200/50 border border-slate-200/60 overflow-hidden">
                            <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide">Validity Period</h3>
                            </div>
                            <div className="p-5 space-y-1">
                                <InfoItem
                                    icon={Calendar}
                                    label="Valid From"
                                    value={rateCard.valid_from
                                        ? new Date(rateCard.valid_from).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
                                        : '—'
                                    }
                                />
                                <InfoItem
                                    icon={Clock}
                                    label="Valid Until"
                                    value={rateCard.valid_until
                                        ? new Date(rateCard.valid_until).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
                                        : 'No expiry'
                                    }
                                />
                            </div>
                        </div>

                        {/* Zones Card */}
                        <div className="bg-white rounded-2xl shadow-sm shadow-slate-200/50 border border-slate-200/60 overflow-hidden">
                            <div className="px-5 py-4 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide">Coverage</h3>
                            </div>
                            <div className="p-5">
                                <div className="flex items-center gap-3">
                                    <div className="flex-1 text-center p-3 rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-100">
                                        <div className="text-[10px] font-bold text-blue-400 uppercase tracking-wider mb-1">Origin</div>
                                        <div className="text-sm font-bold text-blue-700 truncate">
                                            {rateCard.origin_zone_name || rateCard.origin_zone || '—'}
                                        </div>
                                    </div>
                                    <div className="text-slate-300">→</div>
                                    <div className="flex-1 text-center p-3 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-100">
                                        <div className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider mb-1">Destination</div>
                                        <div className="text-sm font-bold text-emerald-700 truncate">
                                            {rateCard.destination_zone_name || rateCard.destination_zone || '—'}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Priority Badge */}
                        <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl p-5 text-white shadow-lg shadow-slate-900/20">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-xs font-medium text-slate-400 uppercase tracking-wide">Priority Level</div>
                                    <div className="text-3xl font-bold mt-1">{rateCard.priority ?? 0}</div>
                                </div>
                                <div className="w-12 h-12 rounded-xl bg-white/10 flex items-center justify-center">
                                    <Layers className="w-6 h-6 text-white/70" />
                                </div>
                            </div>
                            <p className="text-xs text-slate-400 mt-3">Higher priority cards are matched first during quote calculation</p>
                        </div>
                    </div>
                </div>

                <RateLineDialog
                    isOpen={isDialogOpen}
                    onClose={() => setIsDialogOpen(false)}
                    onSave={handleSaveLine}
                    cardId={id}
                    initialData={selectedLine}
                />

                <ImportRatesDialog
                    isOpen={isImportOpen}
                    onClose={() => setIsImportOpen(false)}
                    onSuccess={handleSaveLine}
                    cardId={id}
                />
            </div>
        </div>
    );
}
