import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Copy, Mail } from 'lucide-react';

interface ExportSpotManagerProps {
    showCarrierSpot: boolean;
    showAgentCharges: boolean;
    spotRates: {
        carrierSpotRatePgk: string;
        agentDestChargesFcy: string;
        agentCurrency: string;
        isAllIn?: boolean;
    };
    onUpdate: (field: string, value: string | boolean) => void;
    currencies: string[];
    shipmentDetails?: {
        origin: string;
        destination: string;
        mode: string;
        pieces: number;
        weight: number;
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
        pickupSuburb?: string;
        deliverySuburb?: string;
    };
}

export const ExportSpotManager: React.FC<ExportSpotManagerProps> = ({
    showCarrierSpot,
    showAgentCharges,
    spotRates,
    onUpdate,
    currencies,
    shipmentDetails
}) => {
    const [emailScript, setEmailScript] = useState('');
    const [isCopied, setIsCopied] = useState(false);

    if (!showCarrierSpot && !showAgentCharges) {
        return null;
    }

    const generateEmailScript = () => {
        if (!shipmentDetails) return '';

        const dims = shipmentDetails.dimensions?.map((d, i) =>
            `   ${i + 1}. ${d.pieces}x ${d.package_type || 'Box'} @ ${d.length_cm}x${d.width_cm}x${d.height_cm}cm (${d.gross_weight_kg}kg)`
        ).join('\n') || '   No dimensions provided';

        const pickup = shipmentDetails.pickupSuburb ? `Pickup Location: ${shipmentDetails.pickupSuburb}` : '';
        const delivery = shipmentDetails.deliverySuburb ? `Delivery Location: ${shipmentDetails.deliverySuburb}` : '';
        const addressBlock = [pickup, delivery].filter(Boolean).join('\n');

        return `Subject: Quote Request - ${shipmentDetails.origin} to ${shipmentDetails.destination} - ${shipmentDetails.mode}

Dear Partner,

Please provide D2D destination charges for the following shipment:

Origin: ${shipmentDetails.origin}
Destination: ${shipmentDetails.destination}
Service: ${shipmentDetails.serviceScope}
Mode: ${shipmentDetails.mode}
${addressBlock ? '\n' + addressBlock : ''}

Cargo Details:
Pieces: ${shipmentDetails.pieces}
Weight: ${shipmentDetails.weight} kg
Commodity: ${shipmentDetails.commodity || 'General Cargo'}

Dimensions:
${dims}

Best regards,`;
    };

    const handleCopy = () => {
        navigator.clipboard.writeText(emailScript);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    return (
        <Card className="mb-6 border-blue-200 bg-blue-50/30 shadow-sm">
            <CardHeader className="pb-3 border-b border-blue-100 bg-blue-50/50">
                <CardTitle className="text-lg font-semibold text-blue-900 flex items-center gap-2">
                    <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-200 text-blue-800 text-xs font-bold">2</span>
                    Provide Missing Rates
                </CardTitle>
                <p className="text-sm text-blue-700">
                    We calculated what we could, but some rates are missing. Please provide spot rates below to complete the quote.
                </p>
            </CardHeader>

            <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Carrier Spot Rate (A2A) */}
                {showCarrierSpot && (
                    <div className="space-y-2">
                        <Label htmlFor="carrier-spot">Carrier Spot Rate (PGK)</Label>
                        <div className="relative">
                            <span className="absolute left-3 top-2.5 text-gray-500 text-sm">PGK</span>
                            <Input
                                id="carrier-spot"
                                type="number"
                                className="pl-12"
                                placeholder="0.00"
                                value={spotRates.carrierSpotRatePgk}
                                onChange={(e) => onUpdate('carrierSpotRatePgk', e.target.value)}
                            />
                        </div>
                        <p className="text-xs text-gray-500">Overrides standard freight rate</p>
                        <div className="flex items-center space-x-2 mt-2">
                            <Switch
                                id="all-in-rate"
                                checked={spotRates.isAllIn}
                                onCheckedChange={(checked) => onUpdate('isAllIn', checked)}
                            />
                            <Label htmlFor="all-in-rate" className="text-xs text-gray-600">
                                All-In Rate (Includes Surcharges)
                            </Label>
                        </div>
                    </div>
                )}

                {/* Agent Destination Charges */}
                {showAgentCharges && (
                    <>
                        <div className="space-y-2">
                            <div className="flex justify-between items-center">
                                <Label htmlFor="agent-charges">Agent Dest. Charges (FCY)</Label>
                                <Dialog onOpenChange={(open) => {
                                    if (open) setEmailScript(generateEmailScript());
                                }}>
                                    <DialogTrigger asChild>
                                        <Button variant="ghost" size="sm" className="h-6 px-2 text-xs text-blue-600 hover:text-blue-800">
                                            <Mail className="w-3 h-3 mr-1" />
                                            Draft Email
                                        </Button>
                                    </DialogTrigger>
                                    <DialogContent className="sm:max-w-[500px]">
                                        <DialogHeader>
                                            <DialogTitle>Request Destination Charges</DialogTitle>
                                            <DialogDescription>
                                                Copy this script to request a quote from your destination agent.
                                            </DialogDescription>
                                        </DialogHeader>
                                        <div className="space-y-4 py-4">
                                            <Textarea
                                                value={emailScript}
                                                readOnly
                                                className="h-[300px] font-mono text-sm"
                                            />
                                            <Button onClick={handleCopy} className="w-full">
                                                {isCopied ? (
                                                    <>Copied!</>
                                                ) : (
                                                    <>
                                                        <Copy className="w-4 h-4 mr-2" />
                                                        Copy to Clipboard
                                                    </>
                                                )}
                                            </Button>
                                        </div>
                                    </DialogContent>
                                </Dialog>
                            </div>
                            <Input
                                id="agent-charges"
                                type="number"
                                placeholder="0.00"
                                value={spotRates.agentDestChargesFcy}
                                onChange={(e) => onUpdate('agentDestChargesFcy', e.target.value)}
                            />
                            <p className="text-xs text-gray-500">Clearance & Delivery</p>
                        </div>

                        {/* Agent Currency */}
                        <div className="space-y-2">
                            <Label htmlFor="agent-currency">Agent Currency</Label>
                            <Select
                                value={spotRates.agentCurrency}
                                onValueChange={(val) => onUpdate('agentCurrency', val)}
                            >
                                <SelectTrigger id="agent-currency">
                                    <SelectValue placeholder="Select Currency" />
                                </SelectTrigger>
                                <SelectContent>
                                    {currencies.map((curr) => (
                                        <SelectItem key={curr} value={curr}>
                                            {curr}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </>
                )}
            </CardContent>
        </Card>
    );
};
