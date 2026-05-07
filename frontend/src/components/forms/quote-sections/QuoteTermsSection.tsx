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

const DOMESTIC_AIRPORT_COUNTRY_MAP: Record<string, string> = {
  POM: "PG",
  LAE: "PG",
};

const resolveCountryCode = (location: { country_code?: string | null; code?: string | null } | null) => {
  const explicit = (location?.country_code || "").trim().toUpperCase();
  if (explicit) return explicit;
  const code = (location?.code || "").trim().toUpperCase();
  return DOMESTIC_AIRPORT_COUNTRY_MAP[code] || "";
};

export default function QuoteTermsSection({ user }: QuoteTermsSectionProps) {
  const form = useFormContext<QuoteFormSchemaV3>();
  const { control, setValue } = form;
  const originLocation = useQuoteStore((state) => state.originLocation);
  const destinationLocation = useQuoteStore((state) => state.destinationLocation);
  const serviceScope = useWatch({ control, name: "service_scope" });
  const paymentTerm = useWatch({ control, name: "payment_term" });
  const pricingCounterparty = useWatch({ control, name: "pricing_counterparty" });
  const originCountry = resolveCountryCode(originLocation);
  const destinationCountry = resolveCountryCode(destinationLocation);
  const isImport = destinationCountry === "PG" && originCountry !== "PG";
  const isDomestic = originCountry === "PG" && destinationCountry === "PG";
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
  const counterpartyOptionValues = useMemo(
    () => counterpartyOptions.map((option) => option.value).join("|"),
    [counterpartyOptions],
  );

  useEffect(() => {
    let isActive = true;

    if (!isDomestic || !canLoadCounterpartyHints || !originLocation?.code || !destinationLocation?.code) {
      setCounterpartyHints(null);
      setIsLoadingCounterparties(false);
      if (pricingCounterparty) {
        setValue("pricing_counterparty", undefined, { shouldDirty: false, shouldValidate: true });
      }
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
    isDomestic,
    originLocation?.code,
    pricingCounterparty,
    setValue,
    serviceScope,
  ]);

  useEffect(() => {
    if (!isDomestic || !pricingCounterparty) {
      return;
    }

    const validValues = counterpartyOptionValues ? counterpartyOptionValues.split("|") : [];
    const shouldClearSelection =
      validValues.length <= 1 || !validValues.includes(pricingCounterparty);

    if (shouldClearSelection) {
      setValue("pricing_counterparty", undefined, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }, [counterpartyOptionValues, isDomestic, pricingCounterparty, setValue]);

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
      <FormField
        control={control}
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
        control={control}
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
          control={control}
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
