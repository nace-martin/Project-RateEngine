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
import { UseFormReturn } from "react-hook-form";
import { QuoteFormSchemaV3, V3_SERVICE_SCOPES } from "@/lib/schemas/quoteSchema";

interface ShipmentTermsSectionProps {
    form: UseFormReturn<QuoteFormSchemaV3>;
    validIncoterms: string[];
}

export function ShipmentTermsSection({
    form,
    validIncoterms,
}: ShipmentTermsSectionProps) {
    return (
        <Card>
            <CardHeader>
                <CardTitle>Shipment & Terms</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-6 md:grid-cols-3">
                <FormField
                    control={form.control}
                    name="service_scope"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Service Scope</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                                <FormControl>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select Scope" />
                                    </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                    {Object.entries(V3_SERVICE_SCOPES).map(([key, val]) => (
                                        <SelectItem key={key} value={val}>
                                            {val}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="payment_term"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Payment Term</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                                <FormControl>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select Payment Term" />
                                    </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                    <SelectItem value="PREPAID">Prepaid</SelectItem>
                                    <SelectItem value="COLLECT">Collect</SelectItem>
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="incoterm"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Incoterm</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value} disabled={validIncoterms.length <= 1}>
                                <FormControl>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select Incoterm" />
                                    </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                    {validIncoterms.map((term) => (
                                        <SelectItem key={term} value={term}>{term}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />
            </CardContent>
        </Card>
    );
}
