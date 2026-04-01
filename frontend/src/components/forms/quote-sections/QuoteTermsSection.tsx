"use client";

import { useMemo } from "react";
import { useFormContext, useWatch } from "react-hook-form";

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
  getValidIncoterms,
  type QuoteFormSchemaV3,
  V3_INCOTERMS,
  V3_PAYMENT_TERMS,
} from "@/lib/schemas/quoteSchema";
import { formatPaymentTerm } from "@/lib/display";
import { useQuoteStore } from "@/store/useQuoteStore";

export default function QuoteTermsSection() {
  const form = useFormContext<QuoteFormSchemaV3>();
  const destinationLocation = useQuoteStore((state) => state.destinationLocation);
  const serviceScope = useWatch({ control: form.control, name: "service_scope" });
  const paymentTerm = useWatch({ control: form.control, name: "payment_term" });
  const isImport = destinationLocation?.country_code === "PG";
  const validIncoterms = useMemo(
    () => getValidIncoterms(isImport, serviceScope, paymentTerm),
    [isImport, paymentTerm, serviceScope],
  );

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
      <FormField
        control={form.control}
        name="payment_term"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Payment Term</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select payment term" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {Object.entries(V3_PAYMENT_TERMS).map(([key, value]) => (
                  <SelectItem key={key} value={value}>
                    {formatPaymentTerm(key)}
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
        name="incoterm"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Incoterm</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select incoterm" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {Object.entries(V3_INCOTERMS).map(([key, value]) => (
                  <SelectItem
                    key={key}
                    value={value}
                    disabled={!validIncoterms.includes(value)}
                  >
                    {key} {!validIncoterms.includes(value) ? "(N/A)" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormDescription>
              {isImport ? "Import shipment" : "Export/Domestic shipment"}
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
