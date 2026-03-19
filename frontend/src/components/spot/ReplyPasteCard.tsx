"use client";

/**
 * ReplyPasteCard - Text area for pasting agent rate replies
 * 
 * Features:
 * - Line numbers for reference
 * - Preview of pasted text
 * - Submit to analysis
 */

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { Mail, ArrowRight, FileText, Upload, X } from "lucide-react";
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
    sourceBatchId?: string | null;
}

export function ReplyPasteCard({
    onAnalysisComplete,
    isLoading: externalIsLoading,
    speId,
    missingComponents = [],
    sourceBatchId = null,
}: ReplyPasteCardProps) {
    const [text, setText] = useState("");
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isDraggingFile, setIsDraggingFile] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [internalIsLoading, setInternalIsLoading] = useState(false);
    const submitLockRef = useRef(false);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

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

    const handleFileSelection = (file: File | null) => {
        if (!file) return;
        if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
            setError("Please upload a PDF quote file.");
            return;
        }
        setError(null);
        setSelectedFile(file);
    };

    const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0] ?? null;
        handleFileSelection(file);
    };

    const handleDrop = (event: DragEvent<HTMLDivElement>) => {
        event.preventDefault();
        setIsDraggingFile(false);
        handleFileSelection(event.dataTransfer.files?.[0] ?? null);
    };

    const clearSelectedFile = () => {
        setSelectedFile(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    };

    const handleSubmit = async () => {
        if (submitLockRef.current || isLoading) {
            return;
        }

        setError(null);

        if (!text.trim() && !selectedFile) {
            setError("Please paste the agent reply text or upload a PDF quote.");
            return;
        }

        if (!selectedFile && text.trim().length < 20) {
            setError("Reply seems too short. Please paste the complete email.");
            return;
        }

        submitLockRef.current = true;
        setInternalIsLoading(true);
        try {
            const result = await analyzeSpotReply({
                text,
                file: selectedFile,
                assertions: [],
                speId,
                sourceBatchId: sourceBatchId || undefined,
                sourceKind: "OTHER",
                targetBucket: "mixed",
                label: "Primary SPOT Source",
                sourceReference: selectedFile?.name || undefined,
                useAi: true,
            });
            onAnalysisComplete(result);
        } catch (err) {
            console.error("[SPOT ReplyPasteCard] Analysis error:", err);
            setError(err instanceof Error ? err.message : "Failed to analyze reply");
        } finally {
            setInternalIsLoading(false);
            submitLockRef.current = false;
        }
    };

    const lineCount = text.split('\n').length;

    return (
        <Card className="border-slate-200">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                    <Mail className="h-5 w-5 text-slate-600" />
                    Reply Intake
                </CardTitle>
                <CardDescription>
                    Paste the rate reply you received from the agent or carrier, or upload a PDF quote.
                    The system will extract and classify the information for review.
                </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {getMissingMessage()}

                {sourceBatchId && (
                    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                        Re-analyzing will update the current SPOT source instead of creating a duplicate source entry.
                    </div>
                )}

                {error && (
                    <Alert variant="destructive">
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                <div
                    className={`rounded-lg border border-dashed p-4 transition-colors ${
                        isDraggingFile ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-slate-50/60"
                    }`}
                    onDragOver={(event) => {
                        event.preventDefault();
                        setIsDraggingFile(true);
                    }}
                    onDragLeave={(event) => {
                        event.preventDefault();
                        setIsDraggingFile(false);
                    }}
                    onDrop={handleDrop}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="application/pdf,.pdf"
                        className="hidden"
                        onChange={handleFileInputChange}
                    />
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div className="flex items-start gap-3">
                            <Upload className="mt-0.5 h-4 w-4 text-slate-600" />
                            <div className="space-y-1">
                                <p className="text-sm font-medium text-slate-900">Upload PDF quote</p>
                                <p className="text-sm text-slate-600">
                                    Drag and drop a carrier or agent PDF here, or browse for a file.
                                </p>
                            </div>
                        </div>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isLoading}
                        >
                            Choose PDF
                        </Button>
                    </div>
                    {selectedFile && (
                        <div className="mt-3 flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-sm">
                            <div className="flex items-center gap-2 text-slate-700">
                                <FileText className="h-4 w-4" />
                                <span className="font-medium">{selectedFile.name}</span>
                                <span className="text-slate-500">({Math.max(1, Math.round(selectedFile.size / 1024))} KB)</span>
                            </div>
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={clearSelectedFile}
                                disabled={isLoading}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    )}
                </div>

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
                        {text.trim()
                            ? `${lineCount} lines, ${text.length} characters`
                            : selectedFile
                                ? `Ready to analyze ${selectedFile.name}`
                                : "No text pasted or file selected"}
                    </div>

                    <Button
                        onClick={handleSubmit}
                        disabled={isLoading || (!text.trim() && !selectedFile)}
                    >
                        {isLoading ? "Analyzing..." : (
                            <>
                                Analyze Reply
                                <ArrowRight className="h-4 w-4 ml-2" />
                            </>
                        )}
                    </Button>
                </div>

                {isLoading && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                        {selectedFile
                            ? "Analyzing uploaded document. Scanned PDFs can take a little longer while the system reads the quote."
                            : "Analyzing reply text and classifying charges."}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
