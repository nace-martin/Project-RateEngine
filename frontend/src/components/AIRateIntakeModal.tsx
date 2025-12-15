// frontend/src/components/AIRateIntakeModal.tsx
"use client";

import { useState, useCallback, useRef } from "react";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { parseRatesWithAI, saveSpotChargesForQuote } from "@/lib/api";
import type { SpotChargeLine, SpotChargeBucket, SpotChargeUnitBasis } from "@/lib/types";

interface AIRateIntakeModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    quoteId: string;
    onSuccess: () => void;
}

interface ParsedLine {
    id: string;
    bucket: SpotChargeBucket;
    description: string;
    amount: string;
    currency: string;
    unit_basis: SpotChargeUnitBasis;
    percentage: string;
    minimum: string;
    notes: string;
    confidence: number;
    selected: boolean;
}

type InputMode = "text" | "file";

const BUCKET_OPTIONS: SpotChargeBucket[] = ["ORIGIN", "FREIGHT", "DESTINATION"];
const UNIT_OPTIONS: SpotChargeUnitBasis[] = [
    "PER_KG",
    "PER_SHIPMENT",
    "PER_AWB",
    "MINIMUM",
    "PERCENTAGE",
    "OTHER",
];

export function AIRateIntakeModal({
    open,
    onOpenChange,
    quoteId,
    onSuccess,
}: AIRateIntakeModalProps) {
    const [inputMode, setInputMode] = useState<InputMode>("text");
    const [textInput, setTextInput] = useState("");
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [warnings, setWarnings] = useState<string[]>([]);
    const [parsedLines, setParsedLines] = useState<ParsedLine[]>([]);
    const [showPreview, setShowPreview] = useState(false);
    const [saving, setSaving] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const resetState = useCallback(() => {
        setTextInput("");
        setSelectedFile(null);
        setError(null);
        setWarnings([]);
        setParsedLines([]);
        setShowPreview(false);
        setLoading(false);
        setSaving(false);
    }, []);

    const handleClose = useCallback(() => {
        resetState();
        onOpenChange(false);
    }, [resetState, onOpenChange]);

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            if (file.type !== "application/pdf") {
                setError("Only PDF files are supported.");
                return;
            }
            setSelectedFile(file);
            setError(null);
        }
    }, []);

    const handleParse = useCallback(async () => {
        setLoading(true);
        setError(null);
        setWarnings([]);

        try {
            const result = await parseRatesWithAI(quoteId, textInput, selectedFile);

            if (!result.success) {
                setError(result.error || "Failed to parse rates.");
                setWarnings(result.warnings || []);
                setLoading(false);
                return;
            }

            // Convert API response to editable lines
            const lines: ParsedLine[] = (result.lines || []).map((line, index) => ({
                id: line.id || `temp-${index}`,
                bucket: line.bucket as SpotChargeBucket,
                description: line.description || "",
                amount: line.amount || "",
                currency: line.currency || "AUD",
                unit_basis: line.unit_basis as SpotChargeUnitBasis,
                percentage: line.percentage || "",
                minimum: line.minimum || "",
                notes: line.notes || "",
                confidence: line.confidence ?? 1,
                selected: true,
            }));

            setParsedLines(lines);
            setWarnings(result.warnings || []);
            setShowPreview(true);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to parse rates.");
        } finally {
            setLoading(false);
        }
    }, [quoteId, textInput, selectedFile]);

    const handleLineChange = useCallback(
        (index: number, field: keyof ParsedLine, value: string | boolean) => {
            setParsedLines((prev) => {
                const updated = [...prev];
                updated[index] = { ...updated[index], [field]: value };
                return updated;
            });
        },
        []
    );

    const handleToggleSelect = useCallback((index: number) => {
        setParsedLines((prev) => {
            const updated = [...prev];
            updated[index] = { ...updated[index], selected: !updated[index].selected };
            return updated;
        });
    }, []);

    const handleAccept = useCallback(async () => {
        const selectedLines = parsedLines.filter((line) => line.selected);
        if (selectedLines.length === 0) {
            setError("Please select at least one charge line.");
            return;
        }

        setSaving(true);
        setError(null);

        try {
            // Convert to SpotChargeLine format for API
            const charges: SpotChargeLine[] = selectedLines.map((line) => ({
                bucket: line.bucket,
                description: line.description,
                amount: line.amount || null,
                currency: line.currency,
                unit_basis: line.unit_basis,
                min_charge: line.minimum || null,
                percentage: line.percentage || null,
                notes: line.notes,
            }));

            await saveSpotChargesForQuote(quoteId, charges);
            onSuccess();
            handleClose();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to save charges.");
        } finally {
            setSaving(false);
        }
    }, [parsedLines, quoteId, onSuccess, handleClose]);

    const handleBackToInput = useCallback(() => {
        setShowPreview(false);
    }, []);

    const canParse =
        inputMode === "text" ? textInput.trim().length > 0 : selectedFile !== null;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>AI Rate Intake</DialogTitle>
                    <DialogDescription>
                        Paste rate quote text or upload a PDF. AI will extract charge lines for your review.
                    </DialogDescription>
                </DialogHeader>

                {!showPreview ? (
                    // INPUT VIEW
                    <div className="space-y-4">
                        {/* Mode Toggle */}
                        <div className="flex gap-4">
                            <Button
                                variant={inputMode === "text" ? "default" : "outline"}
                                onClick={() => setInputMode("text")}
                                disabled={loading}
                            >
                                Paste Text
                            </Button>
                            <Button
                                variant={inputMode === "file" ? "default" : "outline"}
                                onClick={() => setInputMode("file")}
                                disabled={loading}
                            >
                                Upload PDF
                            </Button>
                        </div>

                        {/* Text Input */}
                        {inputMode === "text" && (
                            <div className="space-y-2">
                                <label className="text-sm font-medium">
                                    Paste rate quote content (email, quote text)
                                </label>
                                <Textarea
                                    placeholder="Example:&#10;Freight: AUD 2.50/kg (min 250)&#10;Pickup: AUD 85 flat&#10;Fuel Surcharge: 18%"
                                    value={textInput}
                                    onChange={(e) => setTextInput(e.target.value)}
                                    rows={10}
                                    disabled={loading}
                                    className="font-mono text-sm"
                                />
                            </div>
                        )}

                        {/* File Input */}
                        {inputMode === "file" && (
                            <div className="space-y-2">
                                <label className="text-sm font-medium">Upload PDF rate quote</label>
                                <div className="border-2 border-dashed rounded-lg p-8 text-center">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".pdf"
                                        onChange={handleFileSelect}
                                        className="hidden"
                                        disabled={loading}
                                    />
                                    {selectedFile ? (
                                        <div className="space-y-2">
                                            <p className="font-medium">{selectedFile.name}</p>
                                            <p className="text-sm text-muted-foreground">
                                                {(selectedFile.size / 1024).toFixed(1)} KB
                                            </p>
                                            <Button
                                                variant="outline"
                                                onClick={() => setSelectedFile(null)}
                                                disabled={loading}
                                            >
                                                Remove
                                            </Button>
                                        </div>
                                    ) : (
                                        <div className="space-y-2">
                                            <p className="text-muted-foreground">
                                                Click to select or drag and drop a PDF file
                                            </p>
                                            <Button
                                                variant="outline"
                                                onClick={() => fileInputRef.current?.click()}
                                                disabled={loading}
                                            >
                                                Select PDF
                                            </Button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Error Display */}
                        {error && (
                            <div className="bg-destructive/10 text-destructive p-3 rounded-md text-sm">
                                {error}
                            </div>
                        )}

                        {/* Warnings Display */}
                        {warnings.length > 0 && (
                            <div className="bg-yellow-50 text-yellow-800 p-3 rounded-md text-sm">
                                <p className="font-medium">Warnings:</p>
                                <ul className="list-disc list-inside mt-1">
                                    {warnings.map((w, i) => (
                                        <li key={i}>{w}</li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        <DialogFooter>
                            <Button variant="outline" onClick={handleClose} disabled={loading}>
                                Cancel
                            </Button>
                            <Button onClick={handleParse} disabled={!canParse || loading}>
                                {loading ? "Parsing..." : "Parse with AI"}
                            </Button>
                        </DialogFooter>
                    </div>
                ) : (
                    // PREVIEW VIEW
                    <div className="space-y-4">
                        {/* Warnings */}
                        {warnings.length > 0 && (
                            <div className="bg-yellow-50 text-yellow-800 p-3 rounded-md text-sm">
                                <p className="font-medium">AI Parsing Notes:</p>
                                <ul className="list-disc list-inside mt-1">
                                    {warnings.map((w, i) => (
                                        <li key={i}>{w}</li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* Editable Table */}
                        <div className="border rounded-md overflow-x-auto">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-12">Select</TableHead>
                                        <TableHead className="w-28">Bucket</TableHead>
                                        <TableHead>Description</TableHead>
                                        <TableHead className="w-24">Amount</TableHead>
                                        <TableHead className="w-20">Currency</TableHead>
                                        <TableHead className="w-28">Unit</TableHead>
                                        <TableHead className="w-20">Min</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {parsedLines.map((line, index) => (
                                        <TableRow
                                            key={line.id}
                                            className={line.confidence < 0.7 ? "bg-yellow-50" : ""}
                                        >
                                            <TableCell>
                                                <input
                                                    type="checkbox"
                                                    checked={line.selected}
                                                    onChange={() => handleToggleSelect(index)}
                                                    className="h-4 w-4"
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Select
                                                    value={line.bucket}
                                                    onValueChange={(v) =>
                                                        handleLineChange(index, "bucket", v)
                                                    }
                                                >
                                                    <SelectTrigger className="h-8">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {BUCKET_OPTIONS.map((b) => (
                                                            <SelectItem key={b} value={b}>
                                                                {b}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </TableCell>
                                            <TableCell>
                                                <Input
                                                    value={line.description}
                                                    onChange={(e) =>
                                                        handleLineChange(index, "description", e.target.value)
                                                    }
                                                    className="h-8"
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Input
                                                    value={line.amount}
                                                    onChange={(e) =>
                                                        handleLineChange(index, "amount", e.target.value)
                                                    }
                                                    className="h-8 text-right"
                                                    placeholder={line.unit_basis === "PERCENTAGE" ? "—" : "0.00"}
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Input
                                                    value={line.currency}
                                                    onChange={(e) =>
                                                        handleLineChange(index, "currency", e.target.value.toUpperCase())
                                                    }
                                                    className="h-8 w-16"
                                                    maxLength={3}
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Select
                                                    value={line.unit_basis}
                                                    onValueChange={(v) =>
                                                        handleLineChange(index, "unit_basis", v)
                                                    }
                                                >
                                                    <SelectTrigger className="h-8">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {UNIT_OPTIONS.map((u) => (
                                                            <SelectItem key={u} value={u}>
                                                                {u.replace(/_/g, " ")}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </TableCell>
                                            <TableCell>
                                                <Input
                                                    value={line.minimum}
                                                    onChange={(e) =>
                                                        handleLineChange(index, "minimum", e.target.value)
                                                    }
                                                    className="h-8 text-right w-20"
                                                    placeholder="—"
                                                />
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>

                        {parsedLines.length === 0 && (
                            <p className="text-center text-muted-foreground py-4">
                                No charge lines parsed. Try different input.
                            </p>
                        )}

                        {/* Line count */}
                        <p className="text-sm text-muted-foreground">
                            {parsedLines.filter((l) => l.selected).length} of {parsedLines.length} lines
                            selected
                        </p>

                        {/* Error Display */}
                        {error && (
                            <div className="bg-destructive/10 text-destructive p-3 rounded-md text-sm">
                                {error}
                            </div>
                        )}

                        <DialogFooter className="gap-2">
                            <Button variant="outline" onClick={handleBackToInput} disabled={saving}>
                                Back
                            </Button>
                            <Button variant="outline" onClick={handleClose} disabled={saving}>
                                Cancel
                            </Button>
                            <Button
                                onClick={handleAccept}
                                disabled={saving || parsedLines.filter((l) => l.selected).length === 0}
                            >
                                {saving ? "Saving..." : "Accept & Add to Quote"}
                            </Button>
                        </DialogFooter>
                    </div>
                )}
            </DialogContent>
        </Dialog>
    );
}
