"use client";

/**
 * AssertionReviewCard - Interactive table for reviewing/classifying assertions
 * 
 * Features:
 * - Add/edit/remove assertions
 * - Change status (Confirmed/Conditional/Implicit/Missing)
 * - Shows warnings for missing mandatory fields
 * - Summary of assertion counts
 */

import { useState } from "react";
import { Plus, Trash2, AlertTriangle, CheckCircle2, AlertCircle, HelpCircle, XCircle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import type {
    ExtractedAssertion,
    AssertionStatus,
    AssertionCategory,
    AnalysisSummary,
} from "@/lib/reply-analysis-types";
import {
    STATUS_LABELS,
    STATUS_COLORS,
    CATEGORY_LABELS,
    MANDATORY_CATEGORIES,
} from "@/lib/reply-analysis-types";

interface AssertionReviewCardProps {
    assertions: ExtractedAssertion[];
    onUpdate: (assertions: ExtractedAssertion[]) => void;
    summary: AnalysisSummary;
    warnings: string[];
    onProceed: () => void;
    isLoading?: boolean;
}

const STATUS_ICONS: Record<AssertionStatus, React.ReactNode> = {
    confirmed: <CheckCircle2 className="h-4 w-4 text-green-600" />,
    conditional: <AlertCircle className="h-4 w-4 text-amber-600" />,
    implicit: <HelpCircle className="h-4 w-4 text-orange-600" />,
    missing: <XCircle className="h-4 w-4 text-red-600" />,
};

const createEmptyAssertion = (): ExtractedAssertion => ({
    id: `a-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    text: "",
    category: "rate",
    status: "confirmed",
    confidence: 1.0,
});

export function AssertionReviewCard({
    assertions,
    onUpdate,
    summary,
    warnings,
    onProceed,
    isLoading,
}: AssertionReviewCardProps) {

    const addAssertion = () => {
        onUpdate([...assertions, createEmptyAssertion()]);
    };

    const removeAssertion = (id: string) => {
        onUpdate(assertions.filter(a => a.id !== id));
    };

    const updateAssertion = (id: string, field: keyof ExtractedAssertion, value: string) => {
        onUpdate(assertions.map(a =>
            a.id === id ? { ...a, [field]: value } : a
        ));
    };

    // Separate warnings by severity
    const blockingWarnings = warnings.filter(w => w.includes('⛔'));
    const infoWarnings = warnings.filter(w => w.includes('⚠️'));

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                    <div>
                        <CardTitle className="text-lg">Review Assertions</CardTitle>
                        <CardDescription>
                            Classify extracted information from the agent reply
                        </CardDescription>
                    </div>

                    {/* Summary badges */}
                    <div className="flex gap-2">
                        {summary.confirmed_count > 0 && (
                            <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">
                                {summary.confirmed_count} Confirmed
                            </Badge>
                        )}
                        {summary.conditional_count > 0 && (
                            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-300">
                                {summary.conditional_count} Conditional
                            </Badge>
                        )}
                        {summary.implicit_count > 0 && (
                            <Badge variant="outline" className="bg-orange-50 text-orange-700 border-orange-300">
                                {summary.implicit_count} Implicit
                            </Badge>
                        )}
                        {summary.missing_count > 0 && (
                            <Badge variant="outline" className="bg-red-50 text-red-700 border-red-300">
                                {summary.missing_count} Missing
                            </Badge>
                        )}
                    </div>
                </div>
            </CardHeader>

            <CardContent className="space-y-4">
                {/* Blocking warnings */}
                {blockingWarnings.length > 0 && (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertDescription>
                            <ul className="list-disc list-inside">
                                {blockingWarnings.map((w, i) => (
                                    <li key={i}>{w.replace('⛔ ', '')}</li>
                                ))}
                            </ul>
                        </AlertDescription>
                    </Alert>
                )}

                {/* Info warnings */}
                {infoWarnings.length > 0 && (
                    <Alert className="bg-amber-50 border-amber-200">
                        <AlertCircle className="h-4 w-4 text-amber-600" />
                        <AlertDescription className="text-amber-700">
                            <ul className="list-disc list-inside">
                                {infoWarnings.map((w, i) => (
                                    <li key={i}>{w.replace('⚠️ ', '')}</li>
                                ))}
                            </ul>
                        </AlertDescription>
                    </Alert>
                )}

                {/* Assertions table */}
                <div className="space-y-3">
                    {assertions.map((assertion) => (
                        <div
                            key={assertion.id}
                            className={`p-3 rounded-lg border ${STATUS_COLORS[assertion.status]}`}
                        >
                            <div className="grid grid-cols-12 gap-3 items-start">
                                {/* Status icon */}
                                <div className="col-span-1 flex justify-center pt-2">
                                    {STATUS_ICONS[assertion.status]}
                                </div>

                                {/* Text */}
                                <div className="col-span-4">
                                    <Input
                                        value={assertion.text}
                                        onChange={(e) => updateAssertion(assertion.id, 'text', e.target.value)}
                                        placeholder="e.g., USD 10.20/kg"
                                        className="bg-white"
                                    />
                                </div>

                                {/* Category */}
                                <div className="col-span-3">
                                    <Select
                                        value={assertion.category}
                                        onValueChange={(v) => updateAssertion(assertion.id, 'category', v)}
                                    >
                                        <SelectTrigger className="bg-white">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                                                <SelectItem key={value} value={value}>
                                                    {MANDATORY_CATEGORIES.includes(value as AssertionCategory) && (
                                                        <span className="text-red-500 mr-1">*</span>
                                                    )}
                                                    {label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* Status */}
                                <div className="col-span-3">
                                    <Select
                                        value={assertion.status}
                                        onValueChange={(v) => updateAssertion(assertion.id, 'status', v)}
                                    >
                                        <SelectTrigger className="bg-white">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(STATUS_LABELS).map(([value, label]) => (
                                                <SelectItem key={value} value={value}>
                                                    {label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {/* Remove */}
                                <div className="col-span-1">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => removeAssertion(assertion.id)}
                                        className="text-red-500 hover:text-red-700"
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>

                            {/* Additional fields for rate category */}
                            {assertion.category === 'rate' && (
                                <div className="grid grid-cols-12 gap-3 mt-2 ml-8">
                                    <div className="col-span-2">
                                        <Input
                                            type="number"
                                            step="0.01"
                                            placeholder="Amount"
                                            value={assertion.rate_amount || ''}
                                            onChange={(e) => updateAssertion(assertion.id, 'rate_amount' as keyof ExtractedAssertion, e.target.value)}
                                            className="bg-white text-sm"
                                        />
                                    </div>
                                    <div className="col-span-2">
                                        <Select
                                            value={assertion.rate_currency || 'USD'}
                                            onValueChange={(v) => updateAssertion(assertion.id, 'rate_currency' as keyof ExtractedAssertion, v)}
                                        >
                                            <SelectTrigger className="bg-white text-sm">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="USD">USD</SelectItem>
                                                <SelectItem value="AUD">AUD</SelectItem>
                                                <SelectItem value="PGK">PGK</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="col-span-2">
                                        <Select
                                            value={assertion.rate_unit || 'per_kg'}
                                            onValueChange={(v) => updateAssertion(assertion.id, 'rate_unit' as keyof ExtractedAssertion, v)}
                                        >
                                            <SelectTrigger className="bg-white text-sm">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="per_kg">Per KG</SelectItem>
                                                <SelectItem value="flat">Flat</SelectItem>
                                                <SelectItem value="per_awb">Per AWB</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            )}

                            {/* Validity date for validity category */}
                            {assertion.category === 'validity' && (
                                <div className="grid grid-cols-12 gap-3 mt-2 ml-8">
                                    <div className="col-span-4">
                                        <Input
                                            type="date"
                                            value={assertion.validity_date || ''}
                                            onChange={(e) => updateAssertion(assertion.id, 'validity_date' as keyof ExtractedAssertion, e.target.value)}
                                            className="bg-white text-sm"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}

                    {/* Add button */}
                    <Button
                        variant="outline"
                        onClick={addAssertion}
                        className="w-full"
                    >
                        <Plus className="h-4 w-4 mr-2" />
                        Add Assertion
                    </Button>
                </div>

                {/* Proceed button */}
                <div className="pt-4 border-t">
                    <Button
                        onClick={onProceed}
                        disabled={isLoading || !summary.can_proceed}
                        className="w-full"
                        size="lg"
                    >
                        {!summary.can_proceed ? (
                            "Complete Required Fields to Proceed"
                        ) : summary.requires_acknowledgement ? (
                            "Proceed with Acknowledgement Required"
                        ) : (
                            "Proceed to Rate Entry"
                        )}
                    </Button>

                    {!summary.can_proceed && (
                        <p className="text-center text-sm text-muted-foreground mt-2">
                            Missing: {summary.mandatory_missing.join(', ')}
                        </p>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
