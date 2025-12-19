"use client";

/**
 * SpotAcknowledgementModal - Sales acknowledgement for SPOT quotes
 * 
 * Requires exact statement acceptance - no creative wording allowed.
 */

import { useState } from "react";
import { AlertTriangle, Check, FileWarning } from "lucide-react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { SPEConditions } from "@/lib/spot-types";

interface SpotAcknowledgementModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    conditions: SPEConditions;
    onAcknowledge: () => Promise<void>;
    isLoading?: boolean;
}

const ACKNOWLEDGEMENT_STATEMENT =
    "I acknowledge this is a conditional SPOT quote and not guaranteed";

export function SpotAcknowledgementModal({
    open,
    onOpenChange,
    conditions,
    onAcknowledge,
    isLoading = false,
}: SpotAcknowledgementModalProps) {
    const [isChecked, setIsChecked] = useState(false);

    const handleAcknowledge = async () => {
        if (!isChecked) return;
        await onAcknowledge();
        setIsChecked(false);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-amber-700">
                        <FileWarning className="h-5 w-5" />
                        Sales Acknowledgement Required
                    </DialogTitle>
                    <DialogDescription>
                        Before proceeding, you must acknowledge the conditional nature of this SPOT quote.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Conditions Summary */}
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3">
                        <h4 className="font-medium text-amber-800 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4" />
                            Conditions
                        </h4>

                        <ul className="space-y-2 text-sm text-amber-700">
                            {conditions.space_not_confirmed && (
                                <li className="flex items-start gap-2">
                                    <span className="text-amber-500">•</span>
                                    Space is NOT confirmed
                                </li>
                            )}
                            {conditions.airline_acceptance_not_confirmed && (
                                <li className="flex items-start gap-2">
                                    <span className="text-amber-500">•</span>
                                    Airline acceptance is NOT confirmed
                                </li>
                            )}
                            {conditions.conditional_charges_present && (
                                <li className="flex items-start gap-2">
                                    <span className="text-amber-500">•</span>
                                    Conditional charges present (may apply)
                                </li>
                            )}
                            <li className="flex items-start gap-2">
                                <span className="text-amber-500">•</span>
                                Rate validity: {conditions.rate_validity_hours} hours
                            </li>
                            {conditions.notes && (
                                <li className="flex items-start gap-2">
                                    <span className="text-amber-500">•</span>
                                    Notes: {conditions.notes}
                                </li>
                            )}
                        </ul>
                    </div>

                    {/* Acknowledgement Checkbox */}
                    <div className="flex items-start gap-3 p-4 rounded-lg border bg-slate-50">
                        <Checkbox
                            id="acknowledge"
                            checked={isChecked}
                            onCheckedChange={(checked) => setIsChecked(checked === true)}
                            className="mt-0.5"
                        />
                        <Label
                            htmlFor="acknowledge"
                            className="text-sm leading-relaxed cursor-pointer"
                        >
                            {ACKNOWLEDGEMENT_STATEMENT}
                        </Label>
                    </div>
                </div>

                <DialogFooter>
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        disabled={isLoading}
                    >
                        Cancel
                    </Button>
                    <Button
                        onClick={handleAcknowledge}
                        disabled={!isChecked || isLoading}
                        className="bg-amber-600 hover:bg-amber-700"
                    >
                        {isLoading ? (
                            "Processing..."
                        ) : (
                            <>
                                <Check className="h-4 w-4 mr-2" />
                                Acknowledge & Continue
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
