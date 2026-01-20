import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { DataTable } from '@/components/ui/data-table-wrapper';
import { cn } from '@/lib/utils';;

interface SpotDimensionItem {
    pieces: number | string;
    length_cm: number | string;
    width_cm: number | string;
    height_cm: number | string;
    gross_weight_kg: number | string;
    package_type?: string;
}

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
        originCountryCode?: string;
        destinationCountryCode?: string;
        mode: string;
        pieces: number;
        weight: number;
        commodity?: string;
        serviceScope: string;
        dimensions?: SpotDimensionItem[];
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

        // Determine shipment direction based on PNG location
        const isExport = shipmentDetails.originCountryCode === 'PG';
        const isImport = shipmentDetails.destinationCountryCode === 'PG';

        // Determine what address details are needed based on service scope
        let addressPlaceholders = '';
        const scope = shipmentDetails.serviceScope;

        if (isExport && (scope === 'D2D' || scope === 'A2D')) {
            // Export: we need delivery address at destination (overseas)
            addressPlaceholders = `
Delivery Address Required:
Delivery Suburb: ________________
Postcode: ________________`;
        } else if (isImport && (scope === 'D2D' || scope === 'D2A')) {
            // Import: we need pickup address at origin (overseas)
            addressPlaceholders = `
Pickup Address Required:
Pickup Suburb: ________________
Postcode: ________________`;
        }

        return `Subject: Quote Request - ${shipmentDetails.origin} to ${shipmentDetails.destination} - ${shipmentDetails.mode}

Dear Partner,

Please provide ${isExport ? 'destination' : 'origin'} charges for the following shipment:

Origin: ${shipmentDetails.origin}
Destination: ${shipmentDetails.destination}
Service: ${shipmentDetails.serviceScope}
Mode: ${shipmentDetails.mode}
${addressPlaceholders}

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

    const dimensionColumns = [
        { header: "Qty", accessorKey: "pieces" as const },
        { header: "Type", accessorKey: "package_type" as const },
        {
            header: "Dimensions (cm)",
            cell: (item: SpotDimensionItem) => `${item.length_cm} x ${item.width_cm} x ${item.height_cm}`
        },
        { header: "Weight (kg)", accessorKey: "gross_weight_kg" as const },
    ];

    return (
        <Card className="mb-6 border-border shadow-sm">
            <CardHeader className="pb-4 border-b border-border bg-muted/20">
                <CardTitle className="text-lg font-semibold text-primary flex items-center justify-between">
                    <span>Provide Missing Rates</span>
                    <span className="text-sm font-normal text-muted-foreground bg-secondary px-3 py-1 rounded-full">
                        Action Required
                    </span>
                </CardTitle>
                <p className="text-sm text-muted-foreground mt-1">
                    Some rates could not be calculated automatically. Please enter spot rates below.
                </p>
            </CardHeader>

            <CardContent className="pt-6 space-y-6">
                {/* Dimensions Table (if strictly needed context) */}
                {shipmentDetails?.dimensions && shipmentDetails.dimensions.length > 0 && (
                    <div className="space-y-2 mb-4">
                        <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Shipment Dimensions</Label>
                        <DataTable
                            data={shipmentDetails.dimensions}
                            columns={dimensionColumns}
                            keyExtractor={(_, i) => `dim-${i}`}
                            className="bg-background"
                        />
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {/* Carrier Spot Rate (A2A) */}
                    {showCarrierSpot && (
                        <div className="space-y-4 p-4 rounded-lg bg-muted/10 border border-border">
                            <h3 className="font-semibold text-foreground border-b pb-2">Carrier Spot Rate</h3>
                            <div className="space-y-3">
                                <Label htmlFor="carrier-spot">Rate Amount (PGK)</Label>
                                <div className="space-y-1">
                                    <Input
                                        id="carrier-spot"
                                        type="number"
                                        placeholder="0.00"
                                        value={spotRates.carrierSpotRatePgk}
                                        onChange={(e) => onUpdate('carrierSpotRatePgk', e.target.value)}
                                        className="font-medium"
                                    />
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Overrides generic freight</p>
                                </div>
                                <div className="flex items-center space-x-2 pt-2">
                                    <Switch
                                        id="all-in-rate"
                                        checked={spotRates.isAllIn}
                                        onCheckedChange={(checked) => onUpdate('isAllIn', checked)}
                                    />
                                    <Label htmlFor="all-in-rate" className="text-sm text-foreground">
                                        All-In Rate (Includes Surcharges)
                                    </Label>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Agent Destination Charges */}
                    {showAgentCharges && (
                        <div className="space-y-4 p-4 rounded-lg bg-muted/10 border border-border">
                            <div className="flex justify-between items-center border-b pb-2">
                                <h3 className="font-semibold text-foreground">Agent Charges</h3>
                                <Dialog onOpenChange={(open) => {
                                    if (open) setEmailScript(generateEmailScript());
                                }}>
                                    <DialogTrigger asChild>
                                        <Button variant="ghost" size="sm" className="h-8 px-2 text-xs font-medium text-primary hover:text-primary/80 hover:bg-primary/10">
                                            Draft Email
                                        </Button>
                                    </DialogTrigger>
                                    <DialogContent className="sm:max-w-[600px]">
                                        <DialogHeader>
                                            <DialogTitle>Request Agent Quote</DialogTitle>
                                            <DialogDescription>
                                                Use this script to request a quote from your destination agent.
                                            </DialogDescription>
                                        </DialogHeader>
                                        <div className="space-y-4 py-4">
                                            <Textarea
                                                value={emailScript}
                                                onChange={(e) => setEmailScript(e.target.value)}
                                                className="h-[300px] font-mono text-sm bg-muted/50"
                                            />
                                        </div>
                                        <DialogFooter>
                                            <Button onClick={handleCopy} className={cn("w-full sm:w-auto", isCopied ? "bg-success hover:bg-success/90" : "")}>
                                                {isCopied ? "Copied!" : "Copy to Clipboard"}
                                            </Button>
                                        </DialogFooter>
                                    </DialogContent>
                                </Dialog>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2 col-span-2">
                                    <Label htmlFor="agent-charges">Total Charges (FCY)</Label>
                                    <Input
                                        id="agent-charges"
                                        type="number"
                                        placeholder="0.00"
                                        value={spotRates.agentDestChargesFcy}
                                        onChange={(e) => onUpdate('agentDestChargesFcy', e.target.value)}
                                        className="font-medium"
                                    />
                                </div>

                                <div className="space-y-2 col-span-2">
                                    <Label htmlFor="agent-currency">Agent Currency</Label>
                                    <Select
                                        value={spotRates.agentCurrency}
                                        onValueChange={(val) => onUpdate('agentCurrency', val)}
                                    >
                                        <SelectTrigger id="agent-currency" className="bg-background">
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
                            </div>
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
};
