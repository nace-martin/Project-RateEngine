'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { AlertTriangle, Mail, Copy, Check, X, Plane } from 'lucide-react';
import Link from 'next/link';

interface MissingRatesModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSubmit?: () => void; // Optional callback after copying
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
        volumetricWeight?: number;
        commodity?: string;
        serviceScope: string;
        incoterm?: string;
        dimensions?: {
            pieces: number | string;
            length_cm: number | string;
            width_cm: number | string;
            height_cm: number | string;
            gross_weight_kg: number | string;
            package_type?: string;
        }[];
    };
}

export function MissingRatesModal({
    isOpen,
    onClose,
    onSubmit,
    missingRates,
    quoteId,
    shipmentDetails,
}: MissingRatesModalProps) {
    const [emailContent, setEmailContent] = useState('');
    const [isCopied, setIsCopied] = useState(false);

    // Determine what's being requested based on missing rates and service context
    const requestedCharges = useMemo(() => {
        const isExport = shipmentDetails.originCountryCode === 'PG';
        const scope = shipmentDetails.serviceScope;
        const charges: string[] = [];

        if (missingRates.carrier) {
            charges.push('Freight Rate');
        }

        if (missingRates.agent) {
            if (isExport) {
                // Export: Destination charges
                if (scope === 'D2D' || scope === 'A2D') {
                    charges.push('Destination Clearance & Delivery Charges');
                } else {
                    charges.push('Destination Clearance Charges');
                }
            } else {
                // Import: Origin charges
                if (scope === 'D2D' || scope === 'D2A') {
                    charges.push('Origin Collection & Clearance Charges');
                } else {
                    charges.push('Origin Clearance Charges');
                }
            }
        }

        return charges;
    }, [missingRates, shipmentDetails]);

    // Determine service description
    const serviceDescription = useMemo(() => {
        const scope = shipmentDetails.serviceScope;
        const descriptions: Record<string, string> = {
            'D2D': 'Door to Door',
            'D2A': 'Door to Airport',
            'A2D': 'Airport to Door',
            'A2A': 'Airport to Airport',
        };
        return descriptions[scope] || scope;
    }, [shipmentDetails.serviceScope]);

    useEffect(() => {
        if (!shipmentDetails) return;

        const dims = shipmentDetails.dimensions?.map((d, i) =>
            `  ${i + 1}. ${d.pieces}x ${d.package_type || 'Box'} @ ${d.length_cm}×${d.width_cm}×${d.height_cm}cm (${d.gross_weight_kg}kg)`
        ).join('\n') || '  No dimensions provided';

        // Calculate volumetric weight if not provided
        let volWeight = shipmentDetails.volumetricWeight;
        if (!volWeight && shipmentDetails.dimensions?.length) {
            volWeight = shipmentDetails.dimensions.reduce((sum, d) => {
                const pieces = Number(d.pieces) || 1;
                const vol = (Number(d.length_cm) * Number(d.width_cm) * Number(d.height_cm)) / 6000;
                return sum + (pieces * vol);
            }, 0);
        }

        // Build the charges request line
        const chargesRequested = requestedCharges.length > 0
            ? `\nCHARGES REQUIRED\n${requestedCharges.map(c => `• ${c}`).join('\n')}`
            : '';

        const template = `Subject: Rate Request - ${shipmentDetails.origin} → ${shipmentDetails.destination} [${shipmentDetails.serviceScope}]

Hi,

Please provide your charges for the following shipment:
${chargesRequested}

ROUTE
Origin: ${shipmentDetails.origin}
Destination: ${shipmentDetails.destination}
Service: ${serviceDescription} (${shipmentDetails.serviceScope})
Mode: ${shipmentDetails.mode}
${shipmentDetails.incoterm ? `Incoterm: ${shipmentDetails.incoterm}` : ''}

CARGO DETAILS
Pieces: ${shipmentDetails.pieces}
Gross Weight: ${shipmentDetails.weight} kg
Volumetric Weight: ${volWeight ? volWeight.toFixed(1) : 'N/A'} kg
Chargeable Weight: ${shipmentDetails.chargeableWeight} kg
Commodity: ${shipmentDetails.commodity || 'General Cargo'}

DIMENSIONS
${dims}

Please quote in your local currency.

Thanks,`;

        setEmailContent(template);
    }, [shipmentDetails, requestedCharges, serviceDescription]);

    const handleCopy = () => {
        navigator.clipboard.writeText(emailContent);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
        onSubmit?.();
    };

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
                            <h2 className="text-lg font-semibold text-amber-900">Request Partner Quote</h2>
                            <p className="text-sm text-amber-700 mt-0.5">
                                Email your partner for the rates below.
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
                    <div className="ml-4 flex gap-2">
                        <span className="px-2 py-1 bg-blue-100 rounded text-xs font-medium text-blue-700">
                            {shipmentDetails.serviceScope}
                        </span>
                        <span className="px-2 py-1 bg-slate-200 rounded text-xs font-medium text-slate-700">
                            {shipmentDetails.chargeableWeight} kg
                        </span>
                    </div>
                </div>

                {/* Content */}
                <div className="px-6 py-6 space-y-6">
                    {/* What's Missing */}
                    <div className="space-y-3">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">Charges Required</h3>
                        <div className="flex flex-wrap gap-2">
                            {requestedCharges.map((charge) => (
                                <span
                                    key={charge}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-700 rounded-full text-sm font-medium"
                                >
                                    <span className="w-1.5 h-1.5 bg-red-500 rounded-full" />
                                    {charge}
                                </span>
                            ))}
                        </div>
                    </div>

                    {/* Email Template */}
                    <div className="border rounded-lg overflow-hidden">
                        <div className="px-4 py-3 bg-blue-50 flex items-center gap-3 border-b border-blue-100">
                            <Mail className="w-5 h-5 text-blue-600" />
                            <span className="font-medium text-blue-900">Email Template</span>
                        </div>
                        <div className="p-4 space-y-3">
                            <Textarea
                                value={emailContent}
                                onChange={(e) => setEmailContent(e.target.value)}
                                className="h-72 font-mono text-sm"
                            />
                            <Button onClick={handleCopy} className="w-full">
                                {isCopied ? (
                                    <>
                                        <Check className="w-4 h-4 mr-2 text-green-400" />
                                        Copied to Clipboard!
                                    </>
                                ) : (
                                    <>
                                        <Copy className="w-4 h-4 mr-2" />
                                        Copy Email Template
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="sticky bottom-0 bg-white border-t px-6 py-4 space-y-3">
                    {quoteId && (
                        <div className="text-xs text-slate-500 bg-slate-50 px-3 py-2 rounded">
                            💾 Quote saved automatically. You can add rates later from the{' '}
                            <Link href="/quotes" className="text-blue-600 hover:underline">Quotes list</Link>.
                        </div>
                    )}
                    <div className="flex items-center justify-end">
                        <Button variant="outline" onClick={onClose}>
                            {quoteId ? 'Close' : 'Cancel'}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
