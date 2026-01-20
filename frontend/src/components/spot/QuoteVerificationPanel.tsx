"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SpotRateEntryForm } from "./SpotRateEntryForm";
import type { SPEChargeLine, ExtractedAssertion } from "@/lib/spot-types";

interface QuoteVerificationPanelProps {
    rawText: string;
    extractedCharges?: ExtractedAssertion[];
    initialCharges: SPEChargeLine[];
    onSubmit: (charges: Omit<SPEChargeLine, 'id'>[]) => Promise<void>;
    isLoading?: boolean;
    shipmentType?: "EXPORT" | "IMPORT" | "DOMESTIC";
    serviceScope?: string;
}

// Helper to escape regex special characters
function escapeRegExp(string: string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); // $& means the whole matched string
}

function renderHighlightedText(text: string, assertions: ExtractedAssertion[]) {
    if (!text) return <span className="text-muted-foreground italic text-xs">No source text available.</span>;
    if (!assertions || assertions.length === 0) return text;

    // 1. Identify ranges to highlight
    // Basic approach: Find first occurrence of each assertion text
    // (In a real app, backend should provide indices to handle duplicates correctly)
    const ranges: { start: number; end: number; type: string }[] = [];

    // Track occupied indices to avoid overlapping highlights (simple greedy approach)
    const occupied = new Array(text.length).fill(false);

    // Sort assertions by length descending to prioritize longer matches (specific over general)
    const sortedAssertions = [...assertions].sort((a, b) => b.text.length - a.text.length);

    sortedAssertions.forEach(assertion => {
        if (!assertion.text || assertion.text.length < 2) return; // Skip very short matches to reduce noise

        const escapedText = escapeRegExp(assertion.text);
        const regex = new RegExp(escapedText, 'gi'); // Case insensitive search
        let match;

        // Find all occurrences? Or just first? For verification, finding all might be too noisy.
        // Let's find the FIRST valid occurrence that isn't occupied.
        while ((match = regex.exec(text)) !== null) {
            const start = match.index;
            const end = start + match[0].length;

            // Check if range is free
            let isFree = true;
            for (let i = start; i < end; i++) {
                if (occupied[i]) {
                    isFree = false;
                    break;
                }
            }

            if (isFree) {
                // Mark occupied
                for (let i = start; i < end; i++) occupied[i] = true;

                ranges.push({
                    start,
                    end,
                    type: assertion.category
                });
                break; // Only highlight first occurrence per assertion for now
            }
        }
    });

    // 2. Sort ranges by start index
    ranges.sort((a, b) => a.start - b.start);

    // 3. Construct elements
    const elements = [];
    let lastIndex = 0;

    ranges.forEach((range, idx) => {
        // Append text before match
        if (range.start > lastIndex) {
            elements.push(text.slice(lastIndex, range.start));
        }

        // Determine highlight color
        let highlightClass = "bg-yellow-200/50 text-foreground dark:bg-yellow-900/40";
        if (range.type === 'rate') highlightClass = "bg-green-200/50 text-foreground dark:bg-green-900/40 font-semibold";
        if (range.type === 'currency') highlightClass = "bg-blue-200/50 text-foreground dark:bg-blue-900/40 font-semibold";

        // Append highlighted match
        elements.push(
            <mark key={idx} className={`${highlightClass} px-0.5 rounded mx-[1px]`}>
                {text.slice(range.start, range.end)}
            </mark>
        );

        lastIndex = range.end;
    });

    // Append remaining text
    if (lastIndex < text.length) {
        elements.push(text.slice(lastIndex));
    }

    return <>{elements}</>;
}


export function QuoteVerificationPanel({
    rawText,
    extractedCharges = [],
    initialCharges,
    onSubmit,
    isLoading,
    shipmentType,
    serviceScope
}: QuoteVerificationPanelProps) {
    return (
        <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-140px)] min-h-[600px]">
            {/* Left Pane: Raw Text */}
            <div className="w-full lg:w-1/3 h-full flex flex-col">
                <Card className="h-full flex flex-col border-border shadow-sm overflow-hidden bg-muted/10">
                    <CardHeader className="bg-muted/50 py-3 border-b border-border">
                        <CardTitle className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                            <span>📄</span> Source Text
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 overflow-y-auto p-4 font-mono text-sm whitespace-pre-wrap leading-relaxed text-foreground/80 bg-background/50">
                        {renderHighlightedText(rawText, extractedCharges)}
                    </CardContent>
                </Card>
            </div>

            {/* Right Pane: Verification Form */}
            <div className="w-full lg:w-2/3 h-full flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto pr-2 pb-10">
                    <div className="mb-6 space-y-1">
                        <h2 className="text-xl font-bold tracking-tight">Verify Spot Quote</h2>
                        <p className="text-sm text-muted-foreground">
                            Review extracted charges against the source text. Confirm all costs before generating quote.
                        </p>
                    </div>

                    <SpotRateEntryForm
                        initialCharges={initialCharges}
                        suggestedCharges={extractedCharges}
                        onSubmit={onSubmit}
                        isLoading={isLoading}
                        shipmentType={shipmentType}
                        serviceScope={serviceScope}
                    />
                </div>
            </div>
        </div>
    );
}
