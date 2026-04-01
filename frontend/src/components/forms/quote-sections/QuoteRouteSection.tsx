"use client";

import { useFormContext } from "react-hook-form";

import { Plane, Ship } from "lucide-react";

import LocationSearch from "@/components/LocationSearchCombobox";
import {
  getCompletedFieldClass,
  type QuoteFormData,
} from "@/components/forms/quote-sections/quote-section-types";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  V3_LOCATION_TYPES,
} from "@/lib/schemas/quoteSchema";
import { SERVICE_SCOPE_OPTIONS } from "@/lib/display";
import { useQuoteStore } from "@/store/useQuoteStore";

export default function QuoteRouteSection() {
  const form = useFormContext<QuoteFormData>();
  const originLocation = useQuoteStore((state) => state.originLocation);
  const destinationLocation = useQuoteStore((state) => state.destinationLocation);
  const setOriginLocation = useQuoteStore((state) => state.setOriginLocation);
  const setDestinationLocation = useQuoteStore((state) => state.setDestinationLocation);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <FormField
          control={form.control}
          name="mode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Mode</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select mode" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="AIR">
                    <div className="flex items-center gap-2">
                      <Plane className="h-4 w-4" />
                      Air Freight
                    </div>
                  </SelectItem>
                  <SelectItem value="SEA" disabled>
                    <div className="flex items-center gap-2">
                      <Ship className="h-4 w-4" />
                      Sea Freight (Coming Soon)
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="service_scope"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Service Scope</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select scope" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {SERVICE_SCOPE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <div className="relative grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="absolute left-1/2 top-10 z-0 hidden h-0.5 w-8 -translate-x-1/2 bg-border md:block" />

        <FormField
          control={form.control}
          name="origin_location_id"
          render={({ field, fieldState }) => (
            <FormItem className="z-10">
              <FormLabel>Origin ({V3_LOCATION_TYPES.AIRPORT})</FormLabel>
              <FormControl>
                <LocationSearch
                  onSelect={(loc) => {
                    setOriginLocation(loc);
                    field.onChange(loc?.id ?? "");
                    form.setValue("origin_location_type", V3_LOCATION_TYPES.AIRPORT, {
                      shouldDirty: true,
                      shouldValidate: true,
                    });
                    form.setValue("origin_airport", (loc?.code ?? "").toUpperCase(), {
                      shouldDirty: true,
                      shouldValidate: true,
                    });
                  }}
                  value={field.value}
                  selectedLabel={originLocation ? `${originLocation.display_name} (${originLocation.code})` : undefined}
                  placeholder="Search airport..."
                  triggerClassName={getCompletedFieldClass(Boolean(field.value) && (fieldState.isTouched || fieldState.isDirty))}
                />
              </FormControl>
              <FormDescription>
                {originLocation ? `${originLocation.display_name} [${originLocation.country_code}]` : "Search by code or city"}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="destination_location_id"
          render={({ field, fieldState }) => (
            <FormItem className="z-10">
              <FormLabel>Destination ({V3_LOCATION_TYPES.AIRPORT})</FormLabel>
              <FormControl>
                <LocationSearch
                  onSelect={(loc) => {
                    setDestinationLocation(loc);
                    field.onChange(loc?.id ?? "");
                    form.setValue("destination_location_type", V3_LOCATION_TYPES.AIRPORT, {
                      shouldDirty: true,
                      shouldValidate: true,
                    });
                    form.setValue("destination_airport", (loc?.code ?? "").toUpperCase(), {
                      shouldDirty: true,
                      shouldValidate: true,
                    });
                  }}
                  value={field.value}
                  selectedLabel={destinationLocation ? `${destinationLocation.display_name} (${destinationLocation.code})` : undefined}
                  placeholder="Search airport..."
                  triggerClassName={getCompletedFieldClass(Boolean(field.value) && (fieldState.isTouched || fieldState.isDirty))}
                />
              </FormControl>
              <FormDescription>
                {destinationLocation ? `${destinationLocation.display_name} [${destinationLocation.country_code}]` : "Search by code or city"}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
    </div>
  );
}
