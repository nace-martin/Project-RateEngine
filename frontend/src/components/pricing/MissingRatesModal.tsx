'use client';

import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { AlertTriangle, Mail, Copy, Check, X, ArrowRight, Plane } from 'lucide-react';

interface MissingRatesModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit: (spotRates: SpotRates) => void;
    missingRates: {
        carrier: boolean;
        agent: boolean;
    };
    quoteId?: string | null;
    shipmentDetails: {
        origin: string;
        destination: string;
        originCountryCode?: string;
        destinationCountryCode?: string;
        mode: string;
        pieces: number;
        weight: number;
        chargeableWeight: number;
        commodity?: string;
        serviceScope: string;
        dimensions?: {
            pieces: number | string;
            length_cm: number | string;
            width_cm: number | string;
            height_cm: number | string;
            gross_weight_kg: number | string;
            package_type?: string;
        }[];
    };
    currencies?: string[];
    isSubmitting?: boolean;
}

interface SpotRates {
    carrierSpotRatePgk: string;
    agentDestChargesFcy: string;
    agentCurrency: string;
    isAllIn: boolean;
}

export function MissingRatesModal({
    isOpen,
    onClose,
    onSubmit,
    missingRates,
    quoteId,
    shipmentDetails,
    currencies = ['USD', 'AUD', 'EUR', 'GBP', 'NZD', 'SGD'],
    isSubmitting = false,
}: MissingRatesModalProps) {
    const [spotRates, setSpotRates] = useState<SpotRates>({
        carrierSpotRatePgk: '',
        agentDestChargesFcy: '',
        agentCurrency: 'AUD',
        isAllIn: false,
    });
    const [emailContent, setEmailContent] = useState('');
    const [isCopied, setIsCopied] = useState(false);
    const [showEmailPanel, setShowEmailPanel] = useState(false);

    useEffect(() => {
        if (!shipmentDetails) return;

        const dims = shipmentDetails.dimensions?.map((d, i) =>
            `  ${i + 1}. ${d.pieces}x ${d.package_type || 'Box'} @ ${d.length_cm}x${d.width_cm}x${d.height_cm}cm (${d.gross_weight_kg}kg)`
        ).join('\n') || '  No dimensions provided';

        const isExport = shipmentDetails.originCountryCode === 'PG';
        const scope = shipmentDetails.serviceScope;

        let addressPlaceholders = '';
        if (isExport && (scope === 'D2D' || scope === 'A2D')) {
            addressPlaceholders = `\nDelivery Address:\nSuburb: ________________\nPostcode: ________________`;
        } else if (!isExport && (scope === 'D2D' || scope === 'D2A')) {
            addressPlaceholders = `\nPickup Address:\nSuburb: ________________\nPostcode: ________________`;
        }

        const template = `Subject: Rate Request - ${shipmentDetails.origin} → ${shipmentDetails.destination}

Hi,

Please provide your charges for the following shipment:

ROUTE
Origin: ${shipmentDetails.origin}
Destination: ${shipmentDetails.destination}
Service: ${shipmentDetails.serviceScope}
Mode: ${shipmentDetails.mode}
${addressPlaceholders}

CARGO
Pieces: ${shipmentDetails.pieces}
Weight: ${shipmentDetails.weight} kg
Chargeable: ${shipmentDetails.chargeableWeight} kg
Commodity: ${shipmentDetails.commodity || 'General Cargo'}

DIMENSIONS
${dims}

Please quote in your local currency.

Thanks,`;

        setEmailContent(template);
    }, [shipmentDetails]);

    const handleCopy = () => {
        navigator.clipboard.writeText(emailContent);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    const handleSubmit = () => {
        onSubmit(spotRates);
    };

    const canSubmit =
        (!missingRates.carrier || spotRates.carrierSpotRatePgk) &&
        (!missingRates.agent || spotRates.agentDestChargesFcy);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

            <div className="relative w-full max-w-2xl max-h-[90vh] overflow-auto bg-white rounded-xl shadow-2xl mx-4">
                {/* Header */}
                <div className="sticky top-0 bg-amber-50 border-b border-amber-200 px-6 py-4 flex items-start justify-between">
                    <div className="flex gap-3">
                        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
                            <AlertTriangle className="w-5 h-5 text-amber-600" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold text-amber-900">Missing Rate Required</h2>
                            <p className="text-sm text-amber-700 mt-0.5">
                                We need additional information to complete your quote.
                                {quoteId && (
                                    <span className="ml-2 text-xs font-mono bg-amber-200 px-1.5 py-0.5 rounded">
                                        Ref: {quoteId.slice(0, 8)}
                                    </span>
                                )}
                            </p>
                        </div>
                    </div>
                    <button onClick={onClose} className="text-amber-600 hover:text-amber-800 p-1">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Route Summary */}
                <div className="px-6 py-4 bg-slate-50 border-b flex items-center justify-center gap-4">
                    <div className="text-center">
                        <div className="text-xs text-slate-500 uppercase tracking-wide">Origin</div>
                        <div className="font-semibold text-slate-900">{shipmentDetails.origin}</div>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                        <div className="w-8 h-px bg-slate-300" />
                        <Plane className="w-4 h-4" />
                        <div className="w-8 h-px bg-slate-300" />
                    </div>
                    <div className="text-center">
                        <div className="text-xs text-slate-500 uppercase tracking-wide">Destination</div>
                        <div className="font-semibold text-slate-900">{shipmentDetails.destination}</div>
                    </div>
                    <div className="ml-6 px-3 py-1 bg-slate-200 rounded text-sm font-medium text-slate-700">
                        {shipmentDetails.chargeableWeight} kg
                    </div>
                </div>

                {/* Content */}
                <div className="px-6 py-6 space-y-6">
                    {/* What's Missing */}
                    <div className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">What&apos;s Missing</h3>
                        <div className="flex flex-wrap gap-2">
                            {missingRates.carrier && (
                                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-700 rounded-full text-sm font-medium">
                                    <span className="w-1.5 h-1.5 bg-red-500 rounded-full" />
                                    Carrier Freight Rate
                                </span>
                            )}
                            {missingRates.agent && (
                                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-700 rounded-full text-sm font-medium">
                                    <span className="w-1.5 h-1.5 bg-red-500 rounded-full" />
                                    Destination Agent Charges
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Email Partner Section */}
                    <div className="border rounded-lg overflow-hidden">
                        <button
                            onClick={() => setShowEmailPanel(!showEmailPanel)}
                            className="w-full px-4 py-3 bg-blue-50 hover:bg-blue-100 flex items-center justify-between transition-colors"
                        >
                            <div className="flex items-center gap-3">
                                <Mail className="w-5 h-5 text-blue-600" />
                                <span className="font-medium text-blue-900">Email Partner for Quote</span>
                            </div>
                            <ArrowRight className={`w-4 h-4 text-blue-600 transition-transform ${showEmailPanel ? 'rotate-90' : ''}`} />
                        </button>

                        {showEmailPanel && (
                            <div className="p-4 border-t border-blue-100 space-y-3">
                                <Textarea
                                    value={emailContent}
                                    onChange={(e) => setEmailContent(e.target.value)}
                                    className="h-64 font-mono text-sm"
                                />
                                <Button onClick={handleCopy} variant="outline" className="w-full">
                                    {isCopied ? (
                                        <>
                                            <Check className="w-4 h-4 mr-2 text-green-600" />
                                            Copied!
                                        </>
                                    ) : (
                                        <>
                                            <Copy className="w-4 h-4 mr-2" />
                                            Copy to Clipboard
                                        </>
                                    )}
                                </Button>
                            </div>
                        )}
                    </div>

                    {/* Divider */}
                    <div className="relative">
                        <div className="absolute inset-0 flex items-center">
                            <div className="w-full border-t border-slate-200" />
                        </div>
                        <div className="relative flex justify-center text-sm">
                            <span className="bg-white px-4 text-slate-500">Enter rate when received</span>
                        </div>
                    </div>

                    {/* Rate Entry */}
                    <div className="space-y-4">
                        {missingRates.carrier && (
                            <div className="p-4 border rounded-lg bg-slate-50 space-y-3">
                                <Label className="text-sm font-medium text-slate-700">Carrier Freight Rate</Label>
                                <div className="flex gap-3">
                                    <div className="relative flex-1">
                                        <span className="absolute left-3 top-2.5 text-slate-500 text-sm font-medium">PGK</span>
                                        <Input
                                            type="number"
                                            placeholder="0.00"
                                            className="pl-12"
                                            value={spotRates.carrierSpotRatePgk}
                                            onChange={(e) => setSpotRates(prev => ({ ...prev, carrierSpotRatePgk: e.target.value }))}
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Switch
                                        id="all-in"
                                        checked={spotRates.isAllIn}
                                        onCheckedChange={(checked) => setSpotRates(prev => ({ ...prev, isAllIn: checked }))}
                                    />
                                    <Label htmlFor="all-in" className="text-sm text-slate-600">
                                        All-in rate (includes fuel &amp; security surcharges)
                                    </Label>
                                </div>
                            </div>
                        )}

                        {missingRates.agent && (
                            <div className="p-4 border rounded-lg bg-slate-50 space-y-3">
                                <Label className="text-sm font-medium text-slate-700">Destination Agent Charges</Label>
                                <div className="flex gap-3">
                                    <Input
                                        type="number"
                                        placeholder="0.00"
                                        className="flex-1"
                                        value={spotRates.agentDestChargesFcy}
                                        onChange={(e) => setSpotRates(prev => ({ ...prev, agentDestChargesFcy: e.target.value }))}
                                    />
                                    <Select
                                        value={spotRates.agentCurrency}
                                        onValueChange={(val) => setSpotRates(prev => ({ ...prev, agentCurrency: val }))}
                                    >
                                        <SelectTrigger className="w-24">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {currencies.map((curr) => (
                                                <SelectItem key={curr} value={curr}>{curr}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <p className="text-xs text-slate-500">
                                    Total charges including clearance, handling, and delivery to door
                                </p>
                            </div>
                        )}
                    </div>
                </div>

                {/* Footer */}
                <div className="sticky bottom-0 bg-white border-t px-6 py-4 space-y-3">
                    {quoteId && (
                        <div className="text-xs text-slate-500 bg-slate-50 px-3 py-2 rounded">
                            💾 Quote saved automatically. You can complete it later from the{' '}
                            <a href="/quotes" className="text-blue-600 hover:underline">Quotes list</a>.
                        </div>
                    )}
                    <div className="flex items-center justify-between">
                        <Button variant="ghost" onClick={onClose}>
                            {quoteId ? 'Save for Later' : 'Cancel'}
                        </Button>
                        <Button
                            onClick={handleSubmit}
                            disabled={!canSubmit || isSubmitting}
                            className="min-w-[160px]"
                        >
                            {isSubmitting ? 'Calculating...' : 'Recalculate Quote'}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
