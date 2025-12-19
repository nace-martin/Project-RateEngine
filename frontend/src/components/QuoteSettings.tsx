"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Settings } from "lucide-react";

interface QuoteSettingsProps {
    defaultPaymentTerm?: string;
}

export default function QuoteSettings({ defaultPaymentTerm = "collect" }: QuoteSettingsProps) {
    const [customerRef, setCustomerRef] = useState("");
    const [validityPeriod, setValidityPeriod] = useState("14");
    const [paymentTerm, setPaymentTerm] = useState(defaultPaymentTerm);
    const [specialInstructions, setSpecialInstructions] = useState("");
    const [attachTerms, setAttachTerms] = useState(false);

    return (
        <Card className="border-slate-200">
            <CardHeader className="pb-3">
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Settings className="w-4 h-4 text-slate-400" />
                    Quote Settings
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Customer Reference Number */}
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label htmlFor="customer-ref" className="text-xs font-medium text-slate-500">
                            Customer Reference Number
                        </Label>
                        <Input
                            id="customer-ref"
                            placeholder="e.g. PO-2023-001"
                            value={customerRef}
                            onChange={(e) => setCustomerRef(e.target.value)}
                            className="mt-1.5 text-sm"
                        />
                    </div>
                    <div>
                        <Label htmlFor="validity" className="text-xs font-medium text-slate-500">
                            Validity Period
                        </Label>
                        <Select value={validityPeriod} onValueChange={setValidityPeriod}>
                            <SelectTrigger id="validity" className="mt-1.5 text-sm">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="7">7 Days</SelectItem>
                                <SelectItem value="14">14 Days</SelectItem>
                                <SelectItem value="30">30 Days</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>

                {/* Payment Terms */}
                <div>
                    <Label className="text-xs font-medium text-slate-500">
                        Payment Terms
                    </Label>
                    <div className="flex gap-4 mt-2">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="radio"
                                name="payment-term"
                                value="prepaid"
                                checked={paymentTerm === "prepaid"}
                                onChange={(e) => setPaymentTerm(e.target.value)}
                                className="w-4 h-4 text-blue-600 border-slate-300 focus:ring-blue-500"
                            />
                            <span className="text-sm text-slate-700">Prepaid</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="radio"
                                name="payment-term"
                                value="collect"
                                checked={paymentTerm === "collect"}
                                onChange={(e) => setPaymentTerm(e.target.value)}
                                className="w-4 h-4 text-blue-600 border-slate-300 focus:ring-blue-500"
                            />
                            <span className="text-sm text-slate-700">Collect</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="radio"
                                name="payment-term"
                                value="credit"
                                checked={paymentTerm === "credit"}
                                onChange={(e) => setPaymentTerm(e.target.value)}
                                className="w-4 h-4 text-blue-600 border-slate-300 focus:ring-blue-500"
                            />
                            <span className="text-sm text-slate-700">Credit Account (30 Days)</span>
                        </label>
                    </div>
                </div>

                {/* Special Instructions */}
                <div>
                    <Label htmlFor="special-instructions" className="text-xs font-medium text-blue-600">
                        Special Instructions / Remarks
                    </Label>
                    <Textarea
                        id="special-instructions"
                        placeholder="Any specific handling instructions or notes for the customer..."
                        value={specialInstructions}
                        onChange={(e) => setSpecialInstructions(e.target.value)}
                        className="mt-1.5 text-sm min-h-[80px]"
                    />
                </div>

                {/* Attach Terms & Conditions */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                    <div>
                        <div className="text-sm font-medium text-slate-700">
                            Attach Standard Terms & Conditions
                        </div>
                        <div className="text-xs text-slate-500">
                            Includes liability and insurance clauses automatically.
                        </div>
                    </div>
                    <Switch
                        checked={attachTerms}
                        onCheckedChange={setAttachTerms}
                    />
                </div>
            </CardContent>
        </Card>
    );
}
