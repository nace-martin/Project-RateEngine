"use client";

/**
 * SpotEmailDraftCard - Generate SPOT rate request email draft
 * 
 * HARD RULES:
 * - No send button
 * - No email integration
 * - No auto-send or auto-copy
 * - One action only: Copy to Clipboard
 */

import { useState, useMemo, useEffect } from "react";
import { Copy, Check, Mail, AlertTriangle, Search } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { searchCompanies } from "@/lib/api";
import type { CompanySearchResult } from "@/lib/types";
import type { SPECommodity } from "@/lib/spot-types";

interface SpotEmailDraftCardProps {
    originCode: string;
    destinationCode: string;
    commodity: SPECommodity;
    weightKg: number;
    pieces: number;
    dimensions?: {
        pieces: number;
        length_cm: number;
        width_cm: number;
        height_cm: number;
        gross_weight_kg: number;
    }[];
    triggerCode?: string;
    userName?: string;
    serviceScope?: string;
    shipmentType?: "EXPORT" | "IMPORT" | "DOMESTIC";
}

// Commodity display names
const COMMODITY_NAMES: Record<string, string> = {
    'GCR': 'General Cargo',
    'DG': 'Dangerous Goods',
    'PER': 'Perishables',
    'AVI': 'Live Animals',
    'HVC': 'High Value Cargo',
    'HUM': 'Human Remains',
    'OOG': 'Oversized/Heavy',
    'VUL': 'Vulnerable Cargo',
    'TTS': 'Time/Temperature Sensitive',
    'SCR': 'Special Cargo',
};

export function SpotEmailDraftCard({
    originCode,
    destinationCode,
    commodity,
    weightKg,
    pieces,
    dimensions,
    triggerCode,
    userName = "",
    serviceScope,
}: SpotEmailDraftCardProps) {
    const [recipientName, setRecipientName] = useState("");
    const [pickupAddress, setPickupAddress] = useState("");
    const [deliveryAddress, setDeliveryAddress] = useState("");
    const [copied, setCopied] = useState(false);

    // Search state
    const [matchingCompanies, setMatchingCompanies] = useState<CompanySearchResult[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [showSuggestions, setShowSuggestions] = useState(false);

    // Search for companies when recipient name changes
    useEffect(() => {
        const timer = setTimeout(async () => {
            if (recipientName.trim().length >= 2 && showSuggestions) {
                setIsSearching(true);
                try {
                    const results = await searchCompanies(recipientName);
                    setMatchingCompanies(results);
                } catch (err) {
                    console.error("Company search failed:", err);
                } finally {
                    setIsSearching(false);
                }
            } else {
                setMatchingCompanies([]);
            }
        }, 500);

        return () => clearTimeout(timer);
    }, [recipientName, showSuggestions]);

    const handleSelectCompany = (company: CompanySearchResult) => {
        setRecipientName(company.name);
        setMatchingCompanies([]);
        setShowSuggestions(false);
    };

    // Generate email draft
    const { subject, body } = useMemo(() => {
        const sender = userName.trim() || "Commercial Team";
        const recipient = recipientName.trim() || "[Agent / Carrier Name]";
        const commodityDisplay = COMMODITY_NAMES[commodity] || commodity;

        // Build dimensions text
        let dimensionsText = "";
        if (dimensions && dimensions.length > 0) {
            dimensions.forEach((dim) => {
                dimensionsText += `  - ${dim.pieces}x: ${dim.length_cm}×${dim.width_cm}×${dim.height_cm} cm, ${dim.gross_weight_kg} kg\n`;
            });
        } else {
            dimensionsText = `  - ${pieces} piece(s), ${weightKg} kg total\n`;
        }

        // Build conditional notes
        const notes: string[] = [];
        if (commodity === 'DG') {
            notes.push("This shipment is Dangerous Goods. Please advise acceptance and surcharges.");
        } else if (['PER', 'AVI', 'TTS'].includes(commodity)) {
            notes.push("This shipment requires special handling. Please advise conditions.");
        } else if (['HVC', 'VUL'].includes(commodity)) {
            notes.push("This shipment contains high-value/vulnerable cargo. Please advise security requirements.");
        } else if (commodity === 'OOG') {
            notes.push("This shipment is oversized. Please advise dimensional constraints and surcharges.");
        } else if (commodity === 'HUM') {
            notes.push("This shipment contains human remains. Please advise handling requirements.");
        }

        if (triggerCode === 'MULTI_LEG_ROUTING') {
            notes.push("If multiple legs apply, please quote per leg.");
        }

        const notesText = notes.length > 0 ? "\n" + notes.join("\n") + "\n" : "";

        // Determine address label logic
        let addressBlock = "";
        const showPickupInBody = serviceScope?.toUpperCase().trim().startsWith("D") || pickupAddress.trim().length > 0;
        const showDeliveryInBody = serviceScope?.toUpperCase().trim().endsWith("D") || deliveryAddress.trim().length > 0;

        if (showPickupInBody) {
            addressBlock += `Pickup Address: ${pickupAddress.trim() || "[Enter Pickup Address]"}\n`;
        }
        if (showDeliveryInBody) {
            addressBlock += `Delivery Address: ${deliveryAddress.trim() || "[Enter Delivery Address]"}\n`;
        }

        const subject = `SPOT Rate Request – ${originCode} → ${destinationCode} – ${weightKg}kg Airfreight`;

        const body = `Hi ${recipient},

Please provide a SPOT airfreight rate for the shipment below:

Origin: ${originCode}
Destination: ${destinationCode}
Commodity: ${commodityDisplay}
Weight: ${weightKg} kg
Pieces / Dimensions:
${dimensionsText.trimEnd()}
${notesText.trim()}
${addressBlock.trim()}

Thank you,
${sender}`;

        return { subject: subject.trim(), body: body.trim() };
    }, [
        originCode, destinationCode, commodity, weightKg, pieces, dimensions,
        triggerCode, userName, recipientName, serviceScope,
        pickupAddress, deliveryAddress
    ]);

    // Copy to clipboard
    const handleCopy = async () => {
        const fullEmail = `Subject: ${subject}\n\n${body}`;
        try {
            await navigator.clipboard.writeText(fullEmail);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            console.error("Failed to copy:", err);
        }
    };

    // Show both address inputs to ensure the user can find them
    const showPickupInput = true;
    const showDeliveryInput = true;

    return (
        <Card className="border-slate-200">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                    <Mail className="h-5 w-5 text-slate-600" />
                    SPOT Rate Request Email
                </CardTitle>
                <CardDescription>
                    Copy this email draft to request rates from agents or carriers.
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Disclaimer */}
                <Alert className="bg-amber-50 border-amber-200">
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                    <AlertDescription className="text-amber-700 text-sm">
                        This is a draft only. No email will be sent automatically.
                    </AlertDescription>
                </Alert>

                {/* Recipient Input with DB Search */}
                <div className="grid grid-cols-1 gap-4">
                    <div className="relative">
                        <Label htmlFor="recipient" className="text-xs">Agent / Airline Contact (Search Customer Records)</Label>
                        <div className="relative mt-1">
                            <Input
                                id="recipient"
                                placeholder="Search by name..."
                                value={recipientName}
                                onChange={(e) => {
                                    setRecipientName(e.target.value);
                                    setShowSuggestions(true);
                                }}
                                onFocus={() => setShowSuggestions(true)}
                                className="pl-9"
                            />
                            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                            {isSearching && (
                                <div className="absolute right-3 top-2.5">
                                    <div className="animate-spin h-4 w-4 border-2 border-primary border-t-transparent rounded-full" />
                                </div>
                            )}
                        </div>

                        {/* Suggestions Dropdown */}
                        {showSuggestions && matchingCompanies.length > 0 && (
                            <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-md shadow-lg max-h-60 overflow-auto">
                                {matchingCompanies.map((company) => (
                                    <button
                                        key={company.id}
                                        className="w-full text-left px-4 py-2 text-sm hover:bg-slate-50 border-b last:border-0 border-slate-100"
                                        onClick={() => handleSelectCompany(company)}
                                    >
                                        <span className="font-medium">{company.name}</span>
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* Address Inputs */}
                {(showPickupInput || showDeliveryInput) && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {showPickupInput && (
                            <div>
                                <Label htmlFor="pickup" className="text-xs">Pickup Address</Label>
                                <Input
                                    id="pickup"
                                    placeholder="Enter pickup suburb/postcode"
                                    value={pickupAddress}
                                    onChange={(e) => setPickupAddress(e.target.value)}
                                    className="mt-1"
                                />
                            </div>
                        )}
                        {showDeliveryInput && (
                            <div>
                                <Label htmlFor="delivery" className="text-xs">Delivery Address</Label>
                                <Input
                                    id="delivery"
                                    placeholder="Enter delivery suburb/postcode"
                                    value={deliveryAddress}
                                    onChange={(e) => setDeliveryAddress(e.target.value)}
                                    className="mt-1"
                                />
                            </div>
                        )}
                    </div>
                )}

                {/* Subject line */}
                <div>
                    <Label className="text-xs text-muted-foreground">Subject</Label>
                    <div className="mt-1 p-2 bg-slate-50 rounded border text-sm font-mono">
                        {subject}
                    </div>
                </div>

                {/* Email body */}
                <div>
                    <Label className="text-xs text-muted-foreground">Email Body</Label>
                    <Textarea
                        value={body}
                        readOnly
                        rows={16}
                        className="mt-1 font-mono text-sm bg-slate-50 resize-none"
                    />
                </div>

                {/* Copy button - THE ONLY ACTION */}
                <Button
                    onClick={handleCopy}
                    className="w-full"
                    variant={copied ? "outline" : "default"}
                >
                    {copied ? (
                        <>
                            <Check className="h-4 w-4 mr-2 text-green-600" />
                            Copied to Clipboard
                        </>
                    ) : (
                        <>
                            <Copy className="h-4 w-4 mr-2" />
                            Copy to Clipboard
                        </>
                    )}
                </Button>
            </CardContent>
        </Card>
    );
}
