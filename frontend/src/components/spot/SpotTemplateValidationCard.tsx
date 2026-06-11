import React, { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CheckCircle2, AlertTriangle, HelpCircle } from "lucide-react";
import type { TemplateValidation, TemplateFinding } from "@/lib/spot-types";

export interface SpotTemplateValidationCardProps {
    validation?: TemplateValidation;
    onReviewFinding?: (finding: TemplateFinding, comment: string) => Promise<void>;
}

export function SpotTemplateValidationCard({ validation, onReviewFinding }: SpotTemplateValidationCardProps) {
    const [activeReviewIdx, setActiveReviewIdx] = useState<number | null>(null);
    const [comment, setComment] = useState("");
    const [submitting, setSubmitting] = useState(false);

    if (!validation) return null;

    const { status, findings = [] } = validation;

    const handleSubmitReview = async (finding: TemplateFinding) => {
        if (!onReviewFinding) return;
        setSubmitting(true);
        try {
            await onReviewFinding(finding, comment);
            setActiveReviewIdx(null);
            setComment("");
        } catch {
            // Error is handled by parent or alert
        } finally {
            setSubmitting(false);
        }
    };

    const renderFindingsList = (findingsList: TemplateFinding[], isSkyTheme: boolean) => {
        const borderThemeClass = isSkyTheme ? "border-sky-200/50" : "border-amber-200/50";
        const textThemeClass = isSkyTheme ? "text-sky-900" : "text-amber-900";
        const ringThemeClass = isSkyTheme ? "focus:ring-sky-500" : "focus:ring-amber-500";
        const btnThemeClass = isSkyTheme 
            ? "text-sky-700 border-sky-300 hover:bg-sky-100/50" 
            : "text-amber-700 border-amber-300 hover:bg-amber-100/50";
        const confirmBtnThemeClass = isSkyTheme 
            ? "bg-sky-600 hover:bg-sky-700 text-white border-sky-600" 
            : "bg-amber-600 hover:bg-amber-700 text-white border-amber-600";

        return (
            <div className="mt-3 space-y-2.5">
                {findingsList.map((finding, idx) => (
                    <div 
                        key={idx} 
                        className={`py-2.5 border-b ${borderThemeClass} last:border-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3`}
                    >
                        <div className="space-y-1.5 flex-1">
                            <div className={`text-xs leading-relaxed ${textThemeClass}`}>
                                {finding.message}
                            </div>
                            {finding.is_reviewed && finding.review && (
                                <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-emerald-700 bg-emerald-50 border border-emerald-100 rounded px-2 py-0.5 w-fit">
                                    <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-600" />
                                    <span className="font-semibold">Reviewed:</span>
                                    <span>&ldquo;{finding.review.comment || 'No comment'}&rdquo;</span>
                                    {finding.review.reviewed_by && (
                                        <span className="opacity-60">by {finding.review.reviewed_by}</span>
                                    )}
                                </div>
                            )}
                        </div>

                        {!finding.is_reviewed && onReviewFinding && (
                            <div className="shrink-0 flex items-center gap-2">
                                {activeReviewIdx === idx ? (
                                    <div className="flex items-center gap-1.5">
                                        <input
                                            type="text"
                                            placeholder="Comment (optional)..."
                                            value={comment}
                                            onChange={(e) => setComment(e.target.value)}
                                            className={`text-xs px-2 py-1 border border-slate-300 rounded bg-white text-slate-800 focus:outline-none focus:ring-1 ${ringThemeClass} w-44`}
                                            disabled={submitting}
                                        />
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => handleSubmitReview(finding)}
                                            disabled={submitting}
                                            className={`h-7 px-2.5 text-[10px] ${confirmBtnThemeClass}`}
                                        >
                                            {submitting ? "..." : "Confirm"}
                                        </Button>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => {
                                                setActiveReviewIdx(null);
                                                setComment("");
                                            }}
                                            disabled={submitting}
                                            className="h-7 px-2 text-[10px] text-slate-500 hover:bg-slate-100"
                                        >
                                            Cancel
                                        </Button>
                                    </div>
                                ) : (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => {
                                            setActiveReviewIdx(idx);
                                            setComment("");
                                        }}
                                        className={`h-7 px-2.5 text-[10px] bg-white ${btnThemeClass}`}
                                    >
                                        Mark Reviewed
                                    </Button>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        );
    };

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
                <CardContent className="py-4 px-5">
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
                    {findings.length > 0 && renderFindingsList(findings, false)}
                </CardContent>
            </Card>
        );
    }

    // Review = amber/blue review tone (using blue/slate/sky tones as requested instead of red)
    if (status === "review") {
        return (
            <Card className="border-sky-200 bg-sky-50/50">
                <CardContent className="py-4 px-5">
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
                    {findings.length > 0 && renderFindingsList(findings, true)}
                </CardContent>
            </Card>
        );
    }

    return null;
}
