"use client";

import {
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    FormControl,
} from "@/components/ui/form";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Trash2 } from "lucide-react";
import { UseFormReturn, UseFieldArrayReturn } from "react-hook-form";
import { QuoteFormSchemaV3, V3_CARGO_TYPES } from "@/lib/schemas/quoteSchema";

interface CargoDetailsSectionProps {
    form: UseFormReturn<QuoteFormSchemaV3>;
    fields: UseFieldArrayReturn<QuoteFormSchemaV3, "dimensions">["fields"];
    append: UseFieldArrayReturn<QuoteFormSchemaV3, "dimensions">["append"];
    remove: UseFieldArrayReturn<QuoteFormSchemaV3, "dimensions">["remove"];
    cargoMetrics: {
        pieces: number;
        actualWeight: number;
        volumetricWeight: number;
        chargeableWeight: number;
    };
}

export function CargoDetailsSection({
    form,
    fields,
    append,
    remove,
    cargoMetrics,
}: CargoDetailsSectionProps) {
    function addPieceLine() {
        append({
            pieces: 1,
            length_cm: "0",
            width_cm: "0",
            height_cm: "0",
            gross_weight_kg: "0",
            package_type: "Box",
        });
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle>Cargo Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <FormField
                    control={form.control}
                    name="cargo_type"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Cargo Type</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                                <FormControl>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select Cargo Type" />
                                    </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                    {Object.values(V3_CARGO_TYPES).map((type) => (
                                        <SelectItem key={type} value={type}>
                                            {type}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-medium">Dimensions</h3>
                        <Button type="button" variant="outline" size="sm" onClick={addPieceLine}>
                            Add Line
                        </Button>
                    </div>

                    {fields.map((field, index) => (
                        <div key={field.id} className="grid grid-cols-12 gap-2 items-end">
                            <div className="col-span-2">
                                <FormField
                                    control={form.control}
                                    name={`dimensions.${index}.pieces`}
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel className="text-xs">Pieces</FormLabel>
                                            <FormControl>
                                                <Input type="number" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>
                            <div className="col-span-2">
                                <FormField
                                    control={form.control}
                                    name={`dimensions.${index}.length_cm`}
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel className="text-xs">L (cm)</FormLabel>
                                            <FormControl>
                                                <Input type="number" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>
                            <div className="col-span-2">
                                <FormField
                                    control={form.control}
                                    name={`dimensions.${index}.width_cm`}
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel className="text-xs">W (cm)</FormLabel>
                                            <FormControl>
                                                <Input type="number" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>
                            <div className="col-span-2">
                                <FormField
                                    control={form.control}
                                    name={`dimensions.${index}.height_cm`}
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel className="text-xs">H (cm)</FormLabel>
                                            <FormControl>
                                                <Input type="number" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>
                            <div className="col-span-2">
                                <FormField
                                    control={form.control}
                                    name={`dimensions.${index}.gross_weight_kg`}
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel className="text-xs">Weight (kg)</FormLabel>
                                            <FormControl>
                                                <Input type="number" {...field} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>
                            <div className="col-span-2 flex justify-end">
                                {fields.length > 1 && (
                                    <Button type="button" variant="ghost" size="icon" onClick={() => remove(index)}>
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        </div>
                    ))}

                    {/* Metrics Summary */}
                    <div className="bg-muted p-3 rounded-md grid grid-cols-4 gap-4 text-sm">
                        <div>
                            <span className="block text-muted-foreground text-xs">Total Pieces</span>
                            <span className="font-semibold">{cargoMetrics.pieces}</span>
                        </div>
                        <div>
                            <span className="block text-muted-foreground text-xs">Actual Weight</span>
                            <span className="font-semibold">{cargoMetrics.actualWeight} kg</span>
                        </div>
                        <div>
                            <span className="block text-muted-foreground text-xs">Volumetric Weight</span>
                            <span className="font-semibold">{cargoMetrics.volumetricWeight} kg</span>
                        </div>
                        <div>
                            <span className="block text-muted-foreground text-xs">Chargeable Weight</span>
                            <span className="font-semibold text-primary">{cargoMetrics.chargeableWeight} kg</span>
                        </div>
                    </div>

                </div>
            </CardContent>
        </Card>
    );
}
