"use client";

import { useEffect, useMemo, useState } from "react";
import { useFormContext, useWatch } from "react-hook-form";

import { getQuoteCounterpartyHints, type QuoteCounterpartyHints } from "@/lib/api";
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
import { formatPaymentTerm } from "@/lib/display";
import {
  getValidIncoterms,
  type QuoteFormSchemaV3,
  V3_INCOTERMS,
  V3_PAYMENT_TERMS,
} from "@/lib/schemas/quoteSchema";
import type { User } from "@/lib/types";
import { useQuoteStore } from "@/store/useQuoteStore";

interface QuoteTermsSectionProps {
  user?: User | null;
}

export default function QuoteTermsSection({ user }: QuoteTermsSectionProps) {
  const form = useFormContext<QuoteFormSchemaV3>();
  const originLocation = useQuoteStore((state) => state.originLocation);
  const destinationLocation = useQuoteStore((state) => state.destinationLocation);
  const serviceScope = useWatch({ control: form.control, name: "service_scope" });
  const paymentTerm = useWatch({ control: form.control, name: "payment_term" });
  const pricingCounterparty = useWatch({ control: form.control, name: "pricing_counterparty" });
  const isImport = destinationLocation?.country_code === "PG" && originLocation?.country_code !== "PG";
  const isDomestic = originLocation?.country_code === "PG" && destinationLocation?.country_code === "PG";
  const canLoadCounterpartyHints = user?.role === "manager" || user?.role === "admin";
  const [counterpartyHints, setCounterpartyHints] = useState<QuoteCounterpartyHints | null>(null);
  const [isLoadingCounterparties, setIsLoadingCounterparties] = useState(false);

  const validIncoterms = useMemo(
    () => getValidIncoterms(isImport, serviceScope, paymentTerm),
    [isImport, paymentTerm, serviceScope],
  );
  const counterpartyOptions = useMemo(() => {
    if (!counterpartyHints) return [];

    return [
      ...counterpartyHints.agents.map((agent) => ({
        value: `agent:${agent.id}`,
        label: `Agent - ${agent.code} ${agent.name}`,
      })),
      ...counterpartyHints.carriers.map((carrier) => ({
        value: `carrier:${carrier.id}`,
        label: `Carrier - ${carrier.code} ${carrier.name}`,
      })),
    ];
  }, [counterpartyHints]);

  useEffect(() => {
    let isActive = true;

    if (!isDomestic || !canLoadCounterpartyHints || !originLocation?.code || !destinationLocation?.code) {
      setCounterpartyHints(null);
      setIsLoadingCounterparties(false);
      form.setValue("pricing_counterparty", undefined, { shouldDirty: false, shouldValidate: true });
      return () => {
        isActive = false;
      };
    }

    setIsLoadingCounterparties(true);
    getQuoteCounterpartyHints({
      direction: "DOMESTIC",
      serviceScope,
      originAirport: originLocation.code,
      destinationAirport: destinationLocation.code,
      buyCurrency: "PGK",
    })
      .then((hints) => {
        if (isActive) {
          setCounterpartyHints(hints);
        }
      })
      .catch(() => {
        if (isActive) {
          setCounterpartyHints(null);
        }
      })
      .finally(() => {
        if (isActive) {
          setIsLoadingCounterparties(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [
    canLoadCounterpartyHints,
    destinationLocation?.code,
    form,
    isDomestic,
    originLocation?.code,
    serviceScope,
  ]);

  useEffect(() => {
    if (!isDomestic) {
      return;
    }
    const hasCurrentOption = counterpartyOptions.some((option) => option.value === pricingCounterparty);
    if (pricingCounterparty && !hasCurrentOption) {
      form.setValue("pricing_counterparty", undefined, {
        shouldDirty: true,
        shouldValidate: true,
      });
      return;
    }
    if (counterpartyOptions.length === 1 && !pricingCounterparty) {
      form.setValue("pricing_counterparty", counterpartyOptions[0].value, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }, [counterpartyOptions, form, isDomestic, pricingCounterparty]);

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
            <FormDescription>
              Buy-side currency and counterparties are resolved automatically from active V4 pricing data.
            </FormDescription>
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

      {isDomestic && canLoadCounterpartyHints && counterpartyOptions.length > 1 ? (
        <FormField
          control={form.control}
          name="pricing_counterparty"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Buy Counterparty</FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value || undefined}
                disabled={isLoadingCounterparties}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select carrier or agent" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {counterpartyOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormDescription>
                Required when multiple Domestic COGS rows match this lane.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      ) : null}
    </div>
  );
}
