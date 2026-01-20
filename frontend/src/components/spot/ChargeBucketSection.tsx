import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Control, UseFieldArrayRemove, FieldArrayWithId } from "react-hook-form";
import type { SpotFormValues } from "@/lib/schemas/spotSchema";
import type { SPEChargeBucket } from "@/lib/spot-types";
import { SmartMoneyInput } from "./SmartMoneyInput";

interface ChargeBucketSectionProps {
    bucket: { id: SPEChargeBucket; label: string };
    control: Control<SpotFormValues>;
    fields: FieldArrayWithId<SpotFormValues, "charges", "id">[];
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

export function ChargeBucketSection({
    bucket,
    control,
    fields,
    onAdd,
    onRemove
}: ChargeBucketSectionProps) {
    return (
        <Card className="border-border shadow-sm">
            <CardHeader className="pb-4 border-b border-border bg-muted/20">
                <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                        <CardTitle className="text-lg font-semibold text-primary">
                            {bucket.label}
                        </CardTitle>
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
                                            onClick={() => onRemove(index)}
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
