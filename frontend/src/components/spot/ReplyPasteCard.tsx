"use client";

/**
 * ReplyPasteCard - Text area for pasting agent rate replies
 * 
 * Features:
 * - Line numbers for reference
 * - Preview of pasted text
 * - Submit to analysis
 */

import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";
import { Mail, ArrowRight, FileText, Upload, X, Table, AlertTriangle, Activity } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

import { analyzeSpotReply } from "@/lib/api";
import type { ReplyAnalysisResult } from "@/lib/spot-types";
import { detectTableStructure, type StructuredPreview, detectCurrencies, detectUnits } from "@/lib/spot-table-parser";

interface ReplyPasteCardProps {
    onAnalysisComplete: (result: ReplyAnalysisResult) => void;
    isLoading?: boolean;
    speId?: string;
    missingComponents?: string[];
    sourceBatchId?: string | null;
    title?: string;
    description?: string;
    sourceKind?: "AIRLINE" | "AGENT" | "MANUAL" | "OTHER";
    targetBucket?: "airfreight" | "origin_charges" | "destination_charges" | "mixed";
    sourceLabel?: string;
    sourceReference?: string;
    hideMissingMessage?: boolean;
    onDirtyChange?: (isDirty: boolean) => void;
    onSkipToManual?: () => void;
    submitLabel?: string;
}

export function ReplyPasteCard({
    onAnalysisComplete,
    isLoading: externalIsLoading,
    speId,
    missingComponents = [],
    sourceBatchId = null,
    title = "Rate Intake",
    description = "Paste email replies, upload PDF quotes, or add all external rate details here once. Charges will be classified automatically.",
    sourceKind = "OTHER",
    targetBucket = "mixed",
    sourceLabel = "Uploaded rates",
    sourceReference,
    hideMissingMessage = false,
    onDirtyChange,
    onSkipToManual,
    submitLabel = "Analyze Intake",
}: ReplyPasteCardProps) {
    const [text, setText] = useState("");
    const [pastedHtml, setPastedHtml] = useState<string | null>(null);
    const [previewData, setPreviewData] = useState<StructuredPreview | null>(null);
    const [showPreviewDetail, setShowPreviewDetail] = useState(true);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [isDraggingFile, setIsDraggingFile] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [internalIsLoading, setInternalIsLoading] = useState(false);
    const submitLockRef = useRef(false);
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const onDirtyChangeRef = useRef(onDirtyChange);

    const isLoading = externalIsLoading || internalIsLoading;

    useEffect(() => {
        onDirtyChangeRef.current = onDirtyChange;
    }, [onDirtyChange]);

    useEffect(() => {
        const isDirty = Boolean(text.trim() || selectedFile);
        onDirtyChangeRef.current?.(isDirty);

        return () => {
            onDirtyChangeRef.current?.(false);
        };
    }, [selectedFile, text]);

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
            <div className="mb-4 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
                <span className="font-semibold">Missing external rates:</span> Add everything once and it will be mapped to{" "}
                <strong>{unique.join(", ")}</strong>.
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
            setError("Please paste the rate details or upload a PDF quote.");
            return;
        }

        if (!selectedFile && text.trim().length < 20) {
            setError("Input seems too short. Please paste the full rate reply or supporting notes.");
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
                sourceKind,
                targetBucket,
                label: sourceLabel,
                sourceReference: sourceReference || selectedFile?.name || undefined,
                useAi: true,
                structuredIntake: previewData ? (previewData as unknown as Record<string, unknown>) : undefined,
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
                <CardTitle className="flex items-center gap-2 text-lg">
                    <Mail className="h-5 w-5 text-slate-600" />
                    {title}
                </CardTitle>
                <CardDescription>{description}</CardDescription>
            </CardHeader>

            <CardContent className="space-y-4">
                {!hideMissingMessage && getMissingMessage()}

                {sourceBatchId && (
                    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                        Re-analyzing will refresh the current imported source instead of creating a duplicate source entry.
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
                                    Drag and drop any carrier or agent PDF here, or browse for a file. For email replies and mixed rate notes, paste the text below.
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
                        onChange={(e) => {
                            const val = e.target.value;
                            setText(val);
                            if (!val.trim()) {
                                setPastedHtml(null);
                                setPreviewData(null);
                            } else {
                                const parsed = detectTableStructure(val, pastedHtml);
                                setPreviewData(parsed);
                            }
                        }}
                        onPaste={(e) => {
                            const textData = e.clipboardData.getData("text/plain");
                            const htmlData = e.clipboardData.getData("text/html");
                            if (htmlData) {
                                setPastedHtml(htmlData);
                            }
                            const parsed = detectTableStructure(textData || text, htmlData);
                            setPreviewData(parsed);
                        }}
                        placeholder={`Hi,

Please see our rates for the shipment:

A/F: USD 10.20/kg
Origin handling: USD 85 / shipment
Destination fee: PGK 120 / shipment
Valid until: 31 Dec 2024
Routing: SYD-SIN-POM
Subject to space availability

Best regards,
Agent Name`}
                        rows={12}
                        className="pl-12 font-mono text-sm resize-none"
                    />
                </div>

                {/* Structured Preview UI */}
                {previewData && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4 space-y-3">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Table className="h-4.5 w-4.5 text-blue-600" />
                                <span className="text-sm font-semibold text-slate-900">Intake Structure Preview</span>
                                <Badge variant="outline" className={`text-[10px] font-semibold py-0.5 px-2 ${
                                    previewData.source_type === "html"
                                        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                                        : previewData.source_type === "tsv"
                                            ? "border-blue-200 bg-blue-50 text-blue-800"
                                            : "border-slate-200 bg-slate-100 text-slate-700"
                                }`}>
                                    {previewData.source_type === "html"
                                        ? "HTML Table detected"
                                        : previewData.source_type === "tsv"
                                            ? "Spreadsheet copy detected"
                                            : "Plain text"}
                                </Badge>
                            </div>
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-7 text-xs font-medium text-slate-500 hover:text-slate-950"
                                onClick={() => setShowPreviewDetail(prev => !prev)}
                            >
                                {showPreviewDetail ? "Hide Details" : "Show Details"}
                            </Button>
                        </div>

                        {showPreviewDetail && (
                            <div className="space-y-3 pt-1">
                                {/* Warnings List */}
                                {previewData.warnings.length > 0 && (
                                    <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 flex items-start gap-2.5 text-xs text-amber-900">
                                        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                                        <div className="space-y-1">
                                            <div className="font-semibold">Structure Warnings:</div>
                                            <ul className="list-disc pl-4 space-y-0.5">
                                                {previewData.warnings.map((w, idx) => (
                                                    <li key={idx}>{w}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    </div>
                                )}

                                {/* Detected Metadata Grid */}
                                <div className="grid gap-3 sm:grid-cols-2">
                                    <div className="rounded-lg border border-slate-100 bg-white p-3 space-y-1.5 shadow-sm">
                                        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Detected Currencies</div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {detectCurrencies(text).length > 0 ? (
                                                detectCurrencies(text).map((cur: string, idx: number) => (
                                                    <Badge key={idx} variant="outline" className="border-slate-200 text-slate-800 text-[10px] py-0 px-1.5 bg-slate-50/50">
                                                        {cur}
                                                    </Badge>
                                                ))
                                            ) : (
                                                <span className="text-xs text-slate-400 font-medium">None detected</span>
                                            )}
                                        </div>
                                    </div>

                                    <div className="rounded-lg border border-slate-100 bg-white p-3 space-y-1.5 shadow-sm">
                                        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Detected Units / Bases</div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {detectUnits(text).length > 0 ? (
                                                detectUnits(text).map((unit: string, idx: number) => (
                                                    <Badge key={idx} variant="outline" className="border-slate-200 text-slate-800 text-[10px] py-0 px-1.5 bg-slate-50/50">
                                                        {unit}
                                                    </Badge>
                                                ))
                                            ) : (
                                                <span className="text-xs text-slate-400 font-medium">None detected</span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Table Previews */}
                                {previewData.detected_tables.length > 0 && (
                                    <div className="space-y-3">
                                        {previewData.detected_tables.map((table, idx) => (
                                            <div key={idx} className="rounded-lg border border-slate-200 bg-white overflow-hidden shadow-sm">
                                                <div className="bg-slate-50/80 border-b border-slate-200 px-3.5 py-2 text-xs font-semibold text-slate-700 flex justify-between items-center">
                                                    <span className="flex items-center gap-1.5">
                                                        <Activity className="h-3.5 w-3.5 text-slate-500" />
                                                        Table {idx + 1} ({table.columnCount} columns × {table.rows.length + 1} rows)
                                                    </span>
                                                </div>
                                                <div className="overflow-x-auto max-h-60 scrollbar-thin">
                                                    <table className="min-w-full divide-y divide-slate-150 text-xs text-left">
                                                        <thead className="bg-slate-50/40">
                                                            <tr className="divide-x divide-slate-100">
                                                                {table.headers.map((h, i) => (
                                                                    <th key={i} className="px-3.5 py-2 text-slate-500 font-medium">{h}</th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-slate-100 bg-white">
                                                            {table.rows.map((row, rowIdx) => (
                                                                <tr key={rowIdx} className="hover:bg-slate-50/30 divide-x divide-slate-100">
                                                                    {row.map((cell, cellIdx) => (
                                                                        <td key={cellIdx} className="px-3.5 py-2 text-slate-700 font-mono text-[11px] whitespace-nowrap">{cell}</td>
                                                                    ))}
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Detected Sections */}
                                {previewData.detected_sections.length > 0 && (
                                    <div className="rounded-lg border border-slate-100 bg-white p-3 space-y-1.5 shadow-sm">
                                        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Detected Sections</div>
                                        <div className="flex flex-wrap gap-1.5">
                                            {previewData.detected_sections.map((sect, idx) => (
                                                <Badge key={idx} variant="outline" className="border-slate-200 text-slate-800 text-[10px] py-0 px-1.5 bg-slate-50/50 uppercase font-mono">
                                                    {sect}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Global Notes Preview */}
                                {previewData.global_notes && (
                                    <div className="rounded-lg border border-slate-150 bg-slate-50/30 p-3 space-y-1">
                                        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Preserved Text & Context Preview</div>
                                        <pre className="text-[11px] font-mono text-slate-600 leading-relaxed max-h-40 overflow-y-auto whitespace-pre-wrap">
                                            {previewData.global_notes}
                                        </pre>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                <div className="flex justify-between items-center">
                    <div className="text-sm text-muted-foreground flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        {text.trim()
                            ? `${lineCount} lines, ${text.length} characters`
                            : selectedFile
                                ? `Ready to analyze ${selectedFile.name}`
                                : "No text pasted or file selected"}
                    </div>

                    <div className="flex items-center gap-3">
                        {onSkipToManual && !text.trim() && !selectedFile && (
                            <Button
                                variant="outline"
                                onClick={onSkipToManual}
                                disabled={isLoading}
                            >
                                Enter rates manually
                            </Button>
                        )}
                        <Button
                            onClick={handleSubmit}
                            disabled={isLoading || (!text.trim() && !selectedFile)}
                        >
                            {isLoading ? "Analyzing..." : (
                                <>
                                    {submitLabel}
                                    <ArrowRight className="h-4 w-4 ml-2" />
                                </>
                            )}
                        </Button>
                    </div>
                </div>

                {isLoading && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                        {selectedFile
                            ? "Analyzing uploaded document. Scanned PDFs can take a little longer while the system reads the quote."
                            : "Analyzing intake text and classifying charges."}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
