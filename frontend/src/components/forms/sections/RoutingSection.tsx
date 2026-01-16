"use client";

import {
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    FormDescription,
} from "@/components/ui/form";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    CardDescription,
} from "@/components/ui/card";
import LocationSearchCombobox from "@/components/LocationSearchCombobox";
import { UseFormReturn } from "react-hook-form";
import { QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import { LocationSearchResult } from "@/lib/types";

interface RoutingSectionProps {
    form: UseFormReturn<QuoteFormSchemaV3>;
    originLocation: LocationSearchResult | null;
    destinationLocation: LocationSearchResult | null;
    onOriginSelect: (location: LocationSearchResult | null) => void;
    onDestinationSelect: (location: LocationSearchResult | null) => void;
}

export function RoutingSection({
    form,
    originLocation,
    destinationLocation,
    onOriginSelect,
    onDestinationSelect,
}: RoutingSectionProps) {
    return (
        <Card>
            <CardHeader>
                <CardTitle>Routing</CardTitle>
                <CardDescription>
                    Shipment type (import/export/domestic) is detected automatically.
                </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-6 md:grid-cols-2">
                <FormField
                    control={form.control}
                    name="origin_location_id"
                    render={({ field }) => (
                        <FormItem className="flex flex-col">
                            <FormLabel>Origin Location</FormLabel>
                            <LocationSearchCombobox
                                value={field.value || null}
                                selectedLabel={originLocation?.display_name ?? null}
                                onSelect={onOriginSelect}
                            />
                            <FormDescription>Select any supported location (airport, port, city, or address).</FormDescription>
                            <FormMessage />
                        </FormItem>
                    )}
                />

                <FormField
                    control={form.control}
                    name="destination_location_id"
                    render={({ field }) => (
                        <FormItem className="flex flex-col">
                            <FormLabel>Destination Location</FormLabel>
                            <LocationSearchCombobox
                                value={field.value || null}
                                selectedLabel={destinationLocation?.display_name ?? null}
                                onSelect={onDestinationSelect}
                            />
                            <FormDescription>Select any supported location (airport, port, city, or address).</FormDescription>
                            <FormMessage />
                        </FormItem>
                    )}
                />
            </CardContent>
        </Card>
    );
}
