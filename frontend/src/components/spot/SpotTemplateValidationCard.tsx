import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, AlertTriangle, HelpCircle } from "lucide-react";
import type { TemplateValidation } from "@/lib/spot-types";

export interface SpotTemplateValidationCardProps {
    validation?: TemplateValidation;
}

export function SpotTemplateValidationCard({ validation }: SpotTemplateValidationCardProps) {
    if (!validation) return null;

    const { status, findings = [] } = validation;

    // Subtle/neutral/success for passed
    if (status === "passed") {
        return (
            <Card className="border-emerald-100 bg-emerald-50/30">
                <CardContent className="flex items-center gap-3 py-3 px-4">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                    <div className="flex flex-wrap items-center gap-2 text-sm text-emerald-800">
                        <span className="font-semibold text-emerald-950">Template Validation Passed</span>
                        <span className="opacity-80">All expected charge components are present.</span>
                        <Badge variant="outline" className="border-emerald-200 bg-emerald-100 text-emerald-800">
                            Passed
                        </Badge>
                    </div>
                </CardContent>
            </Card>
        );
    }

    // Warnings = amber
    if (status === "warnings") {
        return (
            <Card className="border-amber-200 bg-amber-50/50">
                <CardContent className="space-y-3 py-4 px-5">
                    <div className="flex items-center gap-3">
                        <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
                        <div className="flex flex-wrap items-center gap-2 text-sm text-amber-800">
                            <span className="font-semibold text-amber-950">Review Recommended</span>
                            <span className="opacity-80">Potential discrepancies detected in charge template.</span>
                            <Badge variant="outline" className="border-amber-300 bg-amber-100 text-amber-800">
                                Warning
                            </Badge>
                        </div>
                    </div>
                    {findings.length > 0 && (
                        <ul className="list-disc pl-5 text-xs text-amber-900 space-y-1">
                            {findings.map((finding, idx) => (
                                <li key={idx} className="leading-relaxed">
                                    {finding.message}
                                </li>
                            ))}
                        </ul>
                    )}
                </CardContent>
            </Card>
        );
    }

    // Review = amber/blue review tone (using blue/slate/sky tones as requested instead of red)
    if (status === "review") {
        return (
            <Card className="border-sky-200 bg-sky-50/50">
                <CardContent className="space-y-3 py-4 px-5">
                    <div className="flex items-center gap-3">
                        <HelpCircle className="h-5 w-5 text-sky-600 shrink-0" />
                        <div className="flex flex-wrap items-center gap-2 text-sm text-sky-800">
                            <span className="font-semibold text-sky-950">Review Recommended</span>
                            <span className="opacity-80">Validation differences require verification.</span>
                            <Badge variant="outline" className="border-sky-300 bg-sky-100 text-sky-800">
                                Review
                            </Badge>
                        </div>
                    </div>
                    {findings.length > 0 && (
                        <ul className="list-disc pl-5 text-xs text-sky-900 space-y-1">
                            {findings.map((finding, idx) => (
                                <li key={idx} className="leading-relaxed">
                                    {finding.message}
                                </li>
                            ))}
                        </ul>
                    )}
                </CardContent>
            </Card>
        );
    }

    return null;
}
