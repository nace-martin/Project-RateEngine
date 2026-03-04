"use client";

/**
 * ReplyPasteCard - Text area for pasting agent rate replies
 * 
 * Features:
 * - Line numbers for reference
 * - Preview of pasted text
 * - Submit to analysis
 */

import { useState } from "react";
import { Mail, ArrowRight, FileText } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { analyzeSpotReply } from "@/lib/api";
import type { ReplyAnalysisResult } from "@/lib/spot-types";

interface ReplyPasteCardProps {
    onAnalysisComplete: (result: ReplyAnalysisResult) => void;
    isLoading?: boolean;
    speId?: string;
    missingComponents?: string[];
}

export function ReplyPasteCard({ onAnalysisComplete, isLoading: externalIsLoading, speId, missingComponents = [] }: ReplyPasteCardProps) {
    const [text, setText] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [internalIsLoading, setInternalIsLoading] = useState(false);

    const isLoading = externalIsLoading || internalIsLoading;

    // Helper to format missing components
    const getMissingMessage = () => {
        if (!missingComponents || missingComponents.length === 0) return null;

        // Map codes to friendly names
        const friendlyNames = missingComponents.map(c => {
            const normalized = c.toUpperCase();
            if (normalized === 'DESTINATION_LOCAL') return 'Destination Charges';
            if (normalized === 'ORIGIN_LOCAL') return 'Origin Charges';
            if (normalized === 'FREIGHT') return 'Freight Rate';
            if (normalized.includes('DEST')) return 'Destination Charges';
            if (normalized.includes('ORIGIN')) return 'Origin Charges';
            if (normalized.includes('AIRFREIGHT')) return 'Freight Rate';
            return c.replace(/_/g, ' ');
        });

        // Deduplicate
        const unique = Array.from(new Set(friendlyNames));

        return (
            <div className="bg-blue-50 border border-blue-200 rounded-md p-3 mb-4 text-sm text-blue-800">
                <span className="font-semibold">Hybrid Quote:</span> Standard rates are available for some components.
                Please provide rates for: <strong>{unique.join(', ')}</strong>.
            </div>
        );
    };

    const handleSubmit = async () => {
        setError(null);
        console.log("[SPOT ReplyPasteCard] handleSubmit called, text length:", text.length);

        if (!text.trim()) {
            setError("Please paste the agent reply text");
            return;
        }

        if (text.trim().length < 20) {
            setError("Reply seems too short. Please paste the complete email.");
            return;
        }

        setInternalIsLoading(true);
        try {
            console.log("[SPOT ReplyPasteCard] Calling analyzeSpotReply, speId:", speId);
            const result = await analyzeSpotReply(text, [], speId);
            console.log("[SPOT ReplyPasteCard] Analysis result received:", JSON.stringify(result).substring(0, 200));
            onAnalysisComplete(result);
        } catch (err) {
            console.error("[SPOT ReplyPasteCard] Analysis error:", err);
            setError(err instanceof Error ? err.message : "Failed to analyze reply");
        } finally {
            setInternalIsLoading(false);
        }
    };

    const lineCount = text.split('\n').length;

    return (
        <Card className="border-slate-200">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                    <Mail className="h-5 w-5 text-slate-600" />
                    Paste Agent Reply
                </CardTitle>
                <CardDescription>
                    Paste the rate reply you received from the agent or carrier.
                    The system will help you extract and classify the information.
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {getMissingMessage()}

                {error && (
                    <Alert variant="destructive">
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                <div className="relative">
                    {/* Line numbers */}
                    <div className="absolute left-0 top-0 bottom-0 w-10 bg-slate-50 rounded-l-md border-r border-slate-200 overflow-hidden pointer-events-none">
                        <div className="pt-2 px-2 text-xs text-slate-400 font-mono leading-6">
                            {Array.from({ length: Math.max(lineCount, 10) }, (_, i) => (
                                <div key={i}>{i + 1}</div>
                            ))}
                        </div>
                    </div>

                    {/* Text area */}
                    <Textarea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        placeholder={`Hi,

Please see our rate for the shipment:

A/F: USD 10.20/kg
Valid until: 31 Dec 2024
Routing: SYD-SIN-POM
Subject to space availability

Best regards,
Agent Name`}
                        rows={12}
                        className="pl-12 font-mono text-sm resize-none"
                    />
                </div>

                <div className="flex justify-between items-center">
                    <div className="text-sm text-muted-foreground flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        {text ? `${lineCount} lines, ${text.length} characters` : "No text pasted"}
                    </div>

                    <Button
                        onClick={handleSubmit}
                        disabled={isLoading || !text.trim()}
                    >
                        {isLoading ? "Analyzing..." : (
                            <>
                                Analyze Reply
                                <ArrowRight className="h-4 w-4 ml-2" />
                            </>
                        )}
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}
