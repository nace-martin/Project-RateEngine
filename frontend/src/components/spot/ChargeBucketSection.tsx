import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Control, UseFieldArrayRemove, FieldArrayWithId, useWatch } from "react-hook-form";
import type { SpotFormValues } from "@/lib/schemas/spotSchema";
import type { SPEChargeBucket } from "@/lib/spot-types";
import { SmartMoneyInput } from "./SmartMoneyInput";
import { useConfirm } from "@/hooks/useConfirm";
import { useToast } from "@/context/toast-context";

interface ChargeBucketSectionProps {
    bucket: { id: SPEChargeBucket; label: string };
    control: Control<SpotFormValues>;
    fields: { field: FieldArrayWithId<SpotFormValues, "charges", "id">; index: number }[];
    onAdd: () => void;
    onRemove: UseFieldArrayRemove;
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

export function ChargeBucketSection({
    bucket,
    control,
    fields,
    onAdd,
    onRemove
}: ChargeBucketSectionProps) {
    const confirm = useConfirm();
    const { toast } = useToast();
    const watchedCharges = useWatch({
        control,
        name: "charges",
    });

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
            <CardHeader className="pb-4 border-b border-border bg-muted/20">
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
            <CardContent className="p-0">
                {fields.length > 0 ? (
                        <Table>
                            <TableHeader className="bg-muted/10">
                            <TableRow>
                                <TableHead className="w-[72px]">Line</TableHead>
                                <TableHead className="w-[30%]">Description</TableHead>
                                <TableHead className="w-[25%]">Amount</TableHead>
                                <TableHead className="w-[15%]">Unit</TableHead>
                                <TableHead className="w-[20%]">Source/Flags</TableHead>
                                <TableHead className="w-[5%]"></TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {fields.map(({ field, index }) => (
                                <TableRow key={field.id} className="group align-top">
                                    <TableCell className="align-top py-4">
                                        <div className="inline-flex min-w-[44px] items-center justify-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                                            {index + 1}
                                        </div>
                                    </TableCell>
                                    <TableCell className="align-top py-4">
                                        <FormField
                                            control={control}
                                            name={`charges.${index}.description`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormControl>
                                                        <Input placeholder="Description" {...field} className="h-9" />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />
                                    </TableCell>
                                    <TableCell className="align-top py-4">
                                        <FormField
                                            control={control}
                                            name={`charges.${index}.unit`} // Need to watch unit for conditional min charge
                                            render={({ field: unitField }) => (
                                                <SmartMoneyInput
                                                    control={control}
                                                    index={index}
                                                    currencyName={`charges.${index}.currency`}
                                                    amountName={`charges.${index}.amount`}
                                                    unit={unitField.value}
                                                    showMinCharge={unitField.value === 'min_or_per_kg'}
                                                    minChargeName={`charges.${index}.min_charge`}
                                                />
                                            )}
                                        />
                                    </TableCell>
                                    <TableCell className="align-top py-4">
                                        <FormField
                                            control={control}
                                            name={`charges.${index}.unit`}
                                            render={({ field }) => (
                                                <div className="space-y-2">
                                                    <FormItem>
                                                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                                                            <FormControl>
                                                                <SelectTrigger className="h-9">
                                                                    <SelectValue />
                                                                </SelectTrigger>
                                                            </FormControl>
                                                            <SelectContent>
                                                                {CHARGE_UNITS.map(u => (
                                                                    <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>
                                                                ))}
                                                            </SelectContent>
                                                        </Select>
                                                    </FormItem>
                                                    {field.value === "percentage" && (
                                                        <FormField
                                                            control={control}
                                                            name={`charges.${index}.percentage_basis`}
                                                            render={({ field: basisField }) => (
                                                                <FormItem>
                                                                    <FormControl>
                                                                        <Input placeholder="Basis e.g. FREIGHT" {...basisField} value={basisField.value || ""} className="h-8 text-xs" />
                                                                    </FormControl>
                                                                </FormItem>
                                                            )}
                                                        />
                                                    )}
                                                </div>
                                            )}
                                        />
                                    </TableCell>
                                    <TableCell className="align-top py-4 space-y-2">
                                        <FormField
                                            control={control}
                                            name={`charges.${index}.source_reference`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormControl>
                                                        <Input placeholder="Source Ref" {...field} className="h-8 text-xs" />
                                                    </FormControl>
                                                    <FormMessage />
                                                </FormItem>
                                            )}
                                        />
                                        <div className="flex flex-col gap-1">
                                            {bucket.id === "airfreight" && (
                                                <FormField
                                                    control={control}
                                                    name={`charges.${index}.is_primary_cost`}
                                                    render={({ field }) => (
                                                        <FormItem className="flex items-center space-x-2 space-y-0">
                                                            <FormControl>
                                                                <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                                                            </FormControl>
                                                            <FormLabel className="text-[10px] text-muted-foreground uppercase font-medium">Primary</FormLabel>
                                                        </FormItem>
                                                    )}
                                                />
                                            )}
                                            <FormField
                                                control={control}
                                                name={`charges.${index}.conditional`}
                                                render={({ field }) => (
                                                    <FormItem className="flex items-center space-x-2 space-y-0">
                                                        <FormControl>
                                                            <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                                                        </FormControl>
                                                        <FormLabel className="text-[10px] text-muted-foreground uppercase font-medium">Conditional</FormLabel>
                                                    </FormItem>
                                                )}
                                            />
                                        </div>
                                    </TableCell>
                                    <TableCell className="align-top py-4 text-right">
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => void handleRemove(index)}
                                            className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
                                        >
                                            <span className="sr-only">Remove</span>
                                            <span className="text-xl leading-none">&times;</span>
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                ) : (
                    <div className="p-8 text-center text-muted-foreground text-sm italic">
                        No charges in this section.
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
