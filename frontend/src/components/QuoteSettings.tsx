"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Settings } from "lucide-react";

interface QuoteSettingsProps {
    defaultPaymentTerm?: string;
}

export default function QuoteSettings({ defaultPaymentTerm = "collect" }: QuoteSettingsProps) {
    const [customerRef, setCustomerRef] = useState("");
    const [specialInstructions, setSpecialInstructions] = useState("");
    const [attachTerms, setAttachTerms] = useState(false);

    // Normalize payment term for display
    const normalizedTerm = defaultPaymentTerm.toLowerCase();
    const displayTerm = normalizedTerm === 'credit' ? 'Credit (30 Days)' :
        normalizedTerm.charAt(0).toUpperCase() + normalizedTerm.slice(1);

    return (
        <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-3 border-b border-slate-50 bg-slate-50/50">
                <CardTitle className="text-sm font-semibold flex items-center gap-2 text-slate-700">
                    <Settings className="w-4 h-4 text-slate-400" />
                    Quote Settings
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5 pt-5">
                {/* Customer Reference & Validity Grid */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                        <Label htmlFor="customer-ref" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                            Customer Ref
                        </Label>
                        <Input
                            id="customer-ref"
                            placeholder="e.g. PO-2023-001"
                            value={customerRef}
                            onChange={(e) => setCustomerRef(e.target.value)}
                            className="h-9 text-sm focus-visible:ring-blue-500"
                        />
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                            Validity
                        </Label>
                        <div className="h-9 flex items-center px-3 rounded-md bg-slate-100 border border-slate-200 text-sm text-slate-500 cursor-not-allowed">
                            7 Days
                        </div>
                    </div>
                </div>

                {/* Payment Terms (Read-only) */}
                <div className="space-y-2">
                    <Label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        Payment Terms
                    </Label>
                    <div className="p-3 rounded-md bg-slate-50 border border-slate-200 text-sm font-medium text-slate-700 flex items-center justify-between">
                        <span>{displayTerm}</span>
                    </div>
                </div>

                {/* Special Instructions */}
                <div className="space-y-1.5">
                    <Label htmlFor="special-instructions" className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
                        Remarks / Instructions
                    </Label>
                    <Textarea
                        id="special-instructions"
                        placeholder="Add specific handling instructions..."
                        value={specialInstructions}
                        onChange={(e) => setSpecialInstructions(e.target.value)}
                        className="min-h-[80px] text-sm resize-none focus-visible:ring-blue-500"
                    />
                </div>

                {/* Attach Terms & Conditions */}
                <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                    <div>
                        <div className="text-sm font-medium text-slate-700">
                            Attach Terms & Conditions
                        </div>
                        <div className="text-[10px] text-slate-400 mt-0.5">
                            Auto-attach liability clauses
                        </div>
                    </div>
                    <Switch
                        checked={attachTerms}
                        onCheckedChange={setAttachTerms}
                        className="data-[state=checked]:bg-blue-600"
                    />
                </div>
            </CardContent>
        </Card>
    );
}
