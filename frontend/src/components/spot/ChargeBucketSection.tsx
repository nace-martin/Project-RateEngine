import { useState } from "react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Control, FieldArrayWithId, UseFieldArrayRemove, useWatch } from "react-hook-form";

import { useToast } from "@/context/toast-context";
import { useConfirm } from "@/hooks/useConfirm";
import type { SpotFormValues } from "@/lib/schemas/spotSchema";
import type { SPEChargeBucket, SPEProductCodeSummary } from "@/lib/spot-types";

import { ChargeNormalizationAudit } from "./ChargeNormalizationAudit";
import { SmartMoneyInput } from "./SmartMoneyInput";

interface ChargeBucketSectionProps {
    bucket: { id: SPEChargeBucket; label: string };
    control: Control<SpotFormValues>;
    fields: { field: FieldArrayWithId<SpotFormValues, "charges", "id">; index: number }[];
    onAdd: () => void;
    onRemove: UseFieldArrayRemove;
    onOpenManualReview?: (chargeLine: SpotFormValues["charges"][number]) => void;
    activeChargeLineId?: string | null;
}

const CHARGE_UNITS = [
    { value: "per_kg", label: "Per KG" },
    { value: "flat", label: "Flat" },
    { value: "per_awb", label: "Per AWB" },
    { value: "per_shipment", label: "Per Shipment" },
    { value: "min_or_per_kg", label: "Min or Per KG" },
    { value: "percentage", label: "Percentage" },
    { value: "per_trip", label: "Per Trip" },
    { value: "per_set", label: "Per Set" },
    { value: "per_man", label: "Per Man" },
];

const IMPORTED_SOURCE_MARKERS = [
    "AGENT REPLY",
    "ANALYSIS",
    "RATE INTAKE",
    "UPLOADED RATES",
];

const isImportedChargeLine = (sourceReference?: string | null) => {
    const normalized = String(sourceReference || "").trim().toUpperCase();
    if (!normalized) return false;
    return IMPORTED_SOURCE_MARKERS.some((marker) => normalized.includes(marker));
};

const statusCardClassName = (chargeLine?: SpotFormValues["charges"][number], isActiveRow = false) => {
    if (isActiveRow) return "border-amber-300 bg-amber-50/70";
    if (chargeLine?.manual_resolution_status === "RESOLVED") return "border-sky-200 bg-sky-50/40";
    if (chargeLine?.normalization_status === "AMBIGUOUS") return "border-rose-200 bg-rose-50/50";
    if (chargeLine?.normalization_status === "UNMAPPED") return "border-amber-200 bg-amber-50/50";
    if (chargeLine?.conditional) return "border-slate-300 bg-slate-50/70";
    return "border-slate-200 bg-white";
};

const getEffectiveProductCode = (
    chargeLine?: SpotFormValues["charges"][number]
): SPEProductCodeSummary | null => {
    if (!chargeLine) return null;
    if (chargeLine.manual_resolution_status === "RESOLVED") {
        return (
            chargeLine.manual_resolved_product_code ||
            chargeLine.effective_resolved_product_code ||
            chargeLine.resolved_product_code ||
            null
        );
    }
    return chargeLine.effective_resolved_product_code || chargeLine.resolved_product_code || null;
};

const getSourceEvidenceLabel = (chargeLine?: SpotFormValues["charges"][number]) => {
    if (!chargeLine?.source_excerpt && !chargeLine?.source_reference) return null;
    const lineNumber = chargeLine.source_line_number ? `Line ${chargeLine.source_line_number}` : null;
    const reference = String(chargeLine.source_reference || "").trim();
    return [lineNumber, reference].filter(Boolean).join(" / ") || "Source";
};

export function ChargeBucketSection({
    bucket,
    control,
    fields,
    onAdd,
    onRemove,
    onOpenManualReview,
    activeChargeLineId,
}: ChargeBucketSectionProps) {
    const confirm = useConfirm();
    const { toast } = useToast();
    const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
    const watchedCharges = useWatch({
        control,
        name: "charges",
    });

    const toggleDetails = (fieldId: string) => {
        setExpandedRows((current) => ({
            ...current,
            [fieldId]: !current[fieldId],
        }));
    };

    const handleRemove = async (index: number) => {
        const currentLine = watchedCharges?.[index];
        const lineNumber = fields.findIndex((item) => item.index === index) + 1;
        const description = String(currentLine?.description || "").trim() || `Line ${lineNumber}`;
        const sourceReference = String(currentLine?.source_reference || "").trim();

        if (isImportedChargeLine(sourceReference)) {
            const confirmed = await confirm({
                title: "Remove imported charge line?",
                description: `Line ${lineNumber} (${description}) came from the imported rates. If you remove it, it will stay out of this quote unless you add it back manually or re-import the source.`,
                confirmLabel: "Remove line",
                cancelLabel: "Keep line",
                variant: "destructive",
            });
            if (!confirmed) return;

            onRemove(index);
            toast({
                title: "Imported line removed",
                description: `Line ${lineNumber} was removed from ${bucket.label}.`,
                variant: "success",
            });
            return;
        }

        onRemove(index);
    };

    return (
        <Card className="border-border shadow-sm">
            <CardHeader className="border-b border-border bg-muted/20 pb-4">
                <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                        <div className="flex items-center gap-3">
                            <CardTitle className="text-lg font-semibold text-primary">
                                {bucket.label}
                            </CardTitle>
                            <div className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600">
                                {fields.length} line{fields.length === 1 ? "" : "s"}
                            </div>
                        </div>
                        <CardDescription>
                            {bucket.id === "airfreight" ? "Primary cost line required" : "Enter itemized charges"}
                        </CardDescription>
                    </div>
                    <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={onAdd}
                        className="text-xs"
                    >
                        + Add Item
                    </Button>
                </div>
            </CardHeader>
            <CardContent className="p-4">
                {fields.length > 0 ? (
                    <div className="space-y-3">
                        {fields.map(({ field, index }) => {
                            const chargeLine = watchedCharges?.[index];
                            const isDetailsOpen = Boolean(expandedRows[field.id]);
                            const canOpenManualReview = Boolean(
                                chargeLine?.charge_line_id &&
                                chargeLine?.manual_resolution_status !== "RESOLVED" &&
                                (chargeLine?.normalization_status === "UNMAPPED" ||
                                    chargeLine?.normalization_status === "AMBIGUOUS")
                            );
                            const chargeLineRowId = chargeLine?.charge_line_id
                                ? `charge-line-${chargeLine.charge_line_id}`
                                : undefined;
                            const isActiveRow =
                                Boolean(activeChargeLineId) &&
                                chargeLine?.charge_line_id === activeChargeLineId;
                            const productCode = getEffectiveProductCode(chargeLine);
                            const displayDescription =
                                String(productCode?.description || chargeLine?.description || "").trim() ||
                                "Imported charge";
                            const sourceEvidenceLabel = getSourceEvidenceLabel(chargeLine);

                            return (
                                <div
                                    key={field.id}
                                    id={chargeLineRowId}
                                    className={`rounded-xl border p-4 shadow-sm transition-colors ${statusCardClassName(chargeLine, isActiveRow)}`}
                                >
                                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.9fr)_minmax(170px,0.55fr)_minmax(210px,0.75fr)] lg:items-start">
                                        <div className="min-w-0 space-y-2">
                                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                                Description
                                            </div>
                                            <FormField
                                                control={control}
                                                name={`charges.${index}.description`}
                                                render={({ field }) => (
                                                    <FormItem className="space-y-2">
                                                        <div>
                                                            <div className="whitespace-normal break-words text-base font-semibold leading-6 text-slate-950">
                                                                {displayDescription}
                                                            </div>
                                                            {productCode?.code ? (
                                                                <div className="mt-1 text-xs font-medium text-slate-500">
                                                                    ProductCode {productCode.code}
                                                                </div>
                                                            ) : null}
                                                            {sourceEvidenceLabel ? (
                                                                <Popover>
                                                                    <PopoverTrigger asChild>
                                                                        <Button
                                                                            type="button"
                                                                            variant="ghost"
                                                                            size="sm"
                                                                            className="mt-2 h-7 px-2 text-xs text-primary hover:bg-primary/5"
                                                                        >
                                                                            Source
                                                                        </Button>
                                                                    </PopoverTrigger>
                                                                    <PopoverContent align="start" className="w-96 max-w-[calc(100vw-2rem)] space-y-3 text-sm">
                                                                        <div>
                                                                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                                                                Source
                                                                            </div>
                                                                            <div className="mt-1 text-xs text-slate-600">{sourceEvidenceLabel}</div>
                                                                        </div>
                                                                        {chargeLine?.source_excerpt ? (
                                                                            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-800">
                                                                                {chargeLine.source_excerpt}
                                                                            </div>
                                                                        ) : (
                                                                            <div className="text-sm text-slate-500">No source snippet captured for this line.</div>
                                                                        )}
                                                                        {chargeLine?.source_line_identity ? (
                                                                            <div className="break-all text-xs text-slate-500">
                                                                                {chargeLine.source_line_identity}
                                                                            </div>
                                                                        ) : null}
                                                                    </PopoverContent>
                                                                </Popover>
                                                            ) : null}
                                                        </div>
                                                        <details className="group">
                                                            <summary className="cursor-pointer text-xs font-medium text-slate-500 hover:text-slate-900">
                                                                Edit display label
                                                            </summary>
                                                            <FormControl>
                                                                <Input
                                                                    placeholder="Description"
                                                                    {...field}
                                                                    className="mt-2 h-9 bg-white"
                                                                />
                                                            </FormControl>
                                                        </details>
                                                        <FormMessage />
                                                    </FormItem>
                                                )}
                                            />
                                            <div className="text-xs text-slate-500">
                                                {bucket.label}
                                            </div>
                                        </div>

                                        <div className="space-y-2">
                                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                                Amount
                                            </div>
                                            <FormField
                                                control={control}
                                                name={`charges.${index}.unit`}
                                                render={({ field: unitField }) => (
                                                    <SmartMoneyInput
                                                        control={control}
                                                        index={index}
                                                        currencyName={`charges.${index}.currency`}
                                                        amountName={`charges.${index}.amount`}
                                                        unit={unitField.value}
                                                        showMinCharge={unitField.value === "min_or_per_kg"}
                                                        minChargeName={`charges.${index}.min_charge`}
                                                    />
                                                )}
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                                Unit
                                            </div>
                                            <FormField
                                                control={control}
                                                name={`charges.${index}.unit`}
                                                render={({ field }) => (
                                                    <FormItem>
                                                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                                                            <FormControl>
                                                                <SelectTrigger className="h-8">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                            </FormControl>
                                                            <SelectContent>
                                                                {CHARGE_UNITS.map((unit) => (
                                                                    <SelectItem key={unit.value} value={unit.value}>
                                                                        {unit.label}
                                                                    </SelectItem>
                                                                ))}
                                                            </SelectContent>
                                                        </Select>
                                                        <FormMessage />
                                                    </FormItem>
                                                )}
                                            />
                                        </div>

                                        <div>
                                            <ChargeNormalizationAudit
                                                normalizationStatus={chargeLine?.normalization_status}
                                                normalizationMethod={chargeLine?.normalization_method}
                                                sourceLabel={chargeLine?.source_label}
                                                normalizedLabel={chargeLine?.normalized_label}
                                                resolvedProductCode={chargeLine?.resolved_product_code}
                                                manualResolutionStatus={chargeLine?.manual_resolution_status}
                                                manualResolvedProductCode={chargeLine?.manual_resolved_product_code}
                                                manualResolutionByUsername={chargeLine?.manual_resolution_by_username}
                                                manualResolutionAt={chargeLine?.manual_resolution_at}
                                                canOpenManualReview={canOpenManualReview}
                                                onOpenManualReview={() => {
                                                    if (chargeLine) {
                                                        onOpenManualReview?.(chargeLine);
                                                    }
                                                }}
                                                detailsOpen={isDetailsOpen}
                                                onToggleDetails={() => toggleDetails(field.id)}
                                            >
                                                <div className="grid gap-3">
                                                    <div className="grid gap-3 md:grid-cols-2">
                                                        <FormField
                                                            control={control}
                                                            name={`charges.${index}.source_reference`}
                                                            render={({ field }) => (
                                                                <FormItem>
                                                                    <FormLabel className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                                                        Source reference
                                                                    </FormLabel>
                                                                    <FormControl>
                                                                        <Input placeholder="Source Ref" {...field} className="h-8 text-xs" />
                                                                    </FormControl>
                                                                    <FormMessage />
                                                                </FormItem>
                                                            )}
                                                        />
                                                        {chargeLine?.unit === "percentage" ? (
                                                            <FormField
                                                                control={control}
                                                                name={`charges.${index}.percentage_basis`}
                                                                render={({ field }) => (
                                                                    <FormItem>
                                                                        <FormLabel className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                                                            Percentage basis
                                                                        </FormLabel>
                                                                        <FormControl>
                                                                            <Input
                                                                                placeholder="Basis e.g. FREIGHT"
                                                                                {...field}
                                                                                value={field.value || ""}
                                                                                className="h-8 text-xs"
                                                                            />
                                                                        </FormControl>
                                                                        <FormMessage />
                                                                    </FormItem>
                                                                )}
                                                            />
                                                        ) : null}
                                                    </div>

                                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                                        <div className="flex flex-wrap items-center gap-4">
                                                            {bucket.id === "airfreight" ? (
                                                                <FormField
                                                                    control={control}
                                                                    name={`charges.${index}.is_primary_cost`}
                                                                    render={({ field }) => (
                                                                        <FormItem className="flex items-center space-x-2 space-y-0">
                                                                            <FormControl>
                                                                                <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                                                                            </FormControl>
                                                                            <FormLabel className="text-[10px] font-medium uppercase text-muted-foreground">
                                                                                Primary
                                                                            </FormLabel>
                                                                        </FormItem>
                                                                    )}
                                                                />
                                                            ) : null}
                                                            <FormField
                                                                control={control}
                                                                name={`charges.${index}.conditional`}
                                                                render={({ field }) => (
                                                                    <FormItem className="flex items-center space-x-2 space-y-0">
                                                                        <FormControl>
                                                                            <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                                                                        </FormControl>
                                                                        <FormLabel className="text-[10px] font-medium uppercase text-muted-foreground">
                                                                            Conditional
                                                                        </FormLabel>
                                                                    </FormItem>
                                                                )}
                                                            />
                                                        </div>

                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="sm"
                                                            onClick={() => void handleRemove(index)}
                                                            className="h-7 px-2 text-[11px] text-muted-foreground hover:text-destructive"
                                                        >
                                                            Remove line
                                                        </Button>
                                                    </div>
                                                </div>
                                            </ChargeNormalizationAudit>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    <div className="p-8 text-center text-sm italic text-muted-foreground">
                        No charges in this section.
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
