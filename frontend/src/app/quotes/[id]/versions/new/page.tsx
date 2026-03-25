"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createQuoteVersion, getQuoteV3 } from "@/lib/api";
import type {
  QuoteVersionCreatePayload,
  V3ManualOverride,
  V3QuoteComputeResponse,
} from "@/lib/types";
import { useAuth } from "@/context/auth-context";
import { useToast } from "@/context/toast-context";
import { useConfirm } from "@/hooks/useConfirm";
import PageActionBar from "@/components/navigation/PageActionBar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Loader2, Plus, Trash2 } from "lucide-react";
import PageBackButton from "@/components/navigation/PageBackButton";
import PageCancelButton from "@/components/navigation/PageCancelButton";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useReturnTo } from "@/hooks/useReturnTo";

interface ComponentOption {
  id: string;
  label: string;
  defaultUnit: string;
}

type ManualChargeLine = V3ManualOverride & {
  valid_until?: string;
};

export default function NewQuoteVersionPage() {
  const params = useParams();
  const router = useRouter();
  const { token } = useAuth();
  const { toast } = useToast();
  const confirm = useConfirm();
  const quotationId =
    typeof params.id === "string"
      ? params.id
      : Array.isArray(params.id)
        ? params.id[0]
        : undefined;

  const [quote, setQuote] = useState<V3QuoteComputeResponse | null>(null);
  const [componentOptions, setComponentOptions] = useState<ComponentOption[]>([]);
  const [charges, setCharges] = useState<ManualChargeLine[]>([]);
  const [loadingQuote, setLoadingQuote] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitLockRef = useRef(false);
  const [initialChargesSnapshot, setInitialChargesSnapshot] = useState("[]");

  const defaultCurrency = useMemo(() => {
    if (!quote) {
      return "PGK";
    }
    return (
      quote.output_currency ||
      quote.latest_version?.totals?.total_sell_fcy_currency ||
      "PGK"
    );
  }, [quote]);

  useEffect(() => {
    if (!quotationId) {
      setError("Quote id is missing.");
      setLoadingQuote(false);
      return;
    }

    setLoadingQuote(true);
    (async () => {
      try {
        const data = await getQuoteV3(quotationId);
        setQuote(data);
         const derivedCurrency =
          data.output_currency ||
          data.latest_version?.totals?.total_sell_fcy_currency ||
          "PGK";
        const optionMap = new Map<string, ComponentOption>();
        data.latest_version.lines.forEach((line) => {
          const component = line.service_component;
          if (!optionMap.has(component.id)) {
            optionMap.set(component.id, {
              id: component.id,
              label: `${component.description} (${component.code})`,
              defaultUnit: component.unit || "SHIPMENT",
            });
          }
        });
        const options = Array.from(optionMap.values());
        setComponentOptions(options);

        const payloadOverrides =
          data.latest_version.payload_json?.overrides ?? [];
        if (payloadOverrides.length > 0) {
          const hydratedCharges = payloadOverrides.map((override) => ({
              service_component_id: override.service_component_id,
              cost_fcy: override.cost_fcy,
              currency: override.currency || derivedCurrency,
              unit: override.unit || "SHIPMENT",
              min_charge_fcy: override.min_charge_fcy || "",
              valid_until: override.valid_until,
            }));
          setCharges(hydratedCharges);
          setInitialChargesSnapshot(JSON.stringify(hydratedCharges));
        } else if (options.length > 0) {
          const defaults = data.latest_version.lines
            .filter((line) => line.is_rate_missing)
            .map<ManualChargeLine>((line) => ({
              service_component_id: line.service_component.id,
              cost_fcy: "",
              currency: derivedCurrency,
              unit: line.service_component.unit || "SHIPMENT",
              min_charge_fcy: "",
            }));
          const initialDefaults = defaults.length > 0 ? defaults : [];
          setCharges(initialDefaults);
          setInitialChargesSnapshot(JSON.stringify(initialDefaults));
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to load quote.";
        setError(message);
      } finally {
        setLoadingQuote(false);
      }
    })();
  }, [quotationId]);

  const handleComponentChange = (index: number, value: string) => {
    setCharges((prev) => {
      const updated = [...prev];
      const next = { ...updated[index], service_component_id: value };
      const option = componentOptions.find((opt) => opt.id === value);
      if (option) {
        next.unit = option.defaultUnit;
      }
      updated[index] = next;
      return updated;
    });
  };

  const handleChargeFieldChange = (
    index: number,
    field: keyof ManualChargeLine,
    value: string,
  ) => {
    setCharges((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  const handleAddCharge = () => {
    const defaultComponent = componentOptions[0];
    setCharges((prev) => [
      ...prev,
      {
        service_component_id: defaultComponent?.id ?? "",
        cost_fcy: "",
        currency: defaultCurrency,
        unit: defaultComponent?.defaultUnit ?? "SHIPMENT",
        min_charge_fcy: "",
      },
    ]);
  };

  const handleRemoveCharge = (index: number) => {
    setCharges((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submitLockRef.current) return;

    if (!quotationId) {
      setError("Quote id is missing.");
      return;
    }
    if (charges.length === 0) {
      setError("Add at least one manual rate before saving.");
      return;
    }

    const normalizedCharges = charges.map((charge) => ({
      service_component_id: charge.service_component_id,
      cost_fcy: charge.cost_fcy,
      currency: charge.currency.toUpperCase(),
      unit: charge.unit,
      ...(charge.min_charge_fcy
        ? { min_charge_fcy: charge.min_charge_fcy }
        : {}),
      ...(charge.valid_until ? { valid_until: charge.valid_until } : {}),
    }));

    if (
      normalizedCharges.some(
        (charge) =>
          !charge.service_component_id ||
          !charge.cost_fcy ||
          !charge.currency ||
          !charge.unit,
      )
    ) {
      setError("Each manual rate must include a service, cost, currency, and unit.");
      return;
    }

    const payload: QuoteVersionCreatePayload = {
      charges: normalizedCharges,
    };

    setIsSubmitting(true);
    submitLockRef.current = true;
    setError(null);
    try {
      await createQuoteVersion(token, quotationId, payload);
      toast({
        title: "Manual rates saved",
        description: "The quote version was updated successfully.",
        variant: "success",
      });
      router.push(`/quotes/${quotationId}`);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to save quote version.";
      setError(message);
    } finally {
      setIsSubmitting(false);
      submitLockRef.current = false;
    }
  };
  const isDirty = JSON.stringify(charges) !== initialChargesSnapshot;
  useUnsavedChangesGuard(isDirty);
  const returnTo = useReturnTo();
  const confirmLeave = async () => {
    if (!isDirty) {
      return true;
    }
    return confirm({
      title: "Discard manual rate changes?",
      description: "You have unsaved manual rate changes. Leaving now will discard them.",
      confirmLabel: "Discard changes",
      cancelLabel: "Stay here",
      variant: "destructive",
    });
  };
  const canSubmit = charges.length > 0 && charges.every((charge) => (
    Boolean(charge.service_component_id)
    && Boolean(charge.cost_fcy)
    && Boolean(charge.currency)
    && Boolean(charge.unit)
  ));

  if (loadingQuote) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="mr-2 h-6 w-6 animate-spin" />
        <span>Loading quote details...</span>
      </div>
    );
  }

  const quoteNumber = quote?.quote_number || quotationId;

  return (
    <div className="container mx-auto p-4">
      <PageBackButton
        fallbackHref={`/quotes/${quotationId}`}
        returnTo={returnTo}
        isDirty={isDirty}
        confirmLeave={confirmLeave}
        disabled={isSubmitting}
      />
      <Card>
        <CardHeader>
          <CardTitle>Add Manual Rates to Quote {quoteNumber}</CardTitle>
        </CardHeader>
        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertTitle>Something went wrong</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {!componentOptions.length && (
            <Alert variant="default" className="mb-4">
              <AlertTitle>No components available</AlertTitle>
              <AlertDescription>
                This quote does not contain any service components to override.
                Please compute the quote first before adding manual rates.
              </AlertDescription>
            </Alert>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className={`space-y-6 ${isSubmitting ? "pointer-events-none opacity-70" : ""}`}>
              {charges.map((charge, index) => (
                <div
                  key={`${charge.service_component_id}-${index}`}
                  className="rounded-lg border p-4"
                >
                  <div className="flex items-center justify-between pb-4">
                    <p className="font-semibold">
                      Manual Rate #{index + 1}
                    </p>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveCharge(index)}
                    >
                      <Trash2 className="mr-1 h-4 w-4" />
                      Remove
                    </Button>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="md:col-span-2">
                      <Label>Service Component</Label>
                      <Select
                        value={charge.service_component_id}
                        onValueChange={(value) =>
                          handleComponentChange(index, value)
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select component" />
                        </SelectTrigger>
                        <SelectContent>
                          {componentOptions.map((option) => (
                            <SelectItem key={option.id} value={option.id}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Cost (FCY)</Label>
                      <Input
                        value={charge.cost_fcy}
                        onChange={(event) =>
                          handleChargeFieldChange(
                            index,
                            "cost_fcy",
                            event.target.value,
                          )
                        }
                        placeholder="0.00"
                        required
                      />
                    </div>
                    <div className="grid grid-cols-[2fr_1fr] gap-2">
                      <div>
                        <Label>Currency</Label>
                        <Input
                          value={charge.currency}
                          maxLength={3}
                          onChange={(event) =>
                            handleChargeFieldChange(
                              index,
                              "currency",
                              event.target.value.toUpperCase(),
                            )
                          }
                          placeholder="PGK"
                          required
                        />
                      </div>
                      <div>
                        <Label>Unit</Label>
                        <Input
                          value={charge.unit}
                          onChange={(event) =>
                            handleChargeFieldChange(
                              index,
                              "unit",
                              event.target.value,
                            )
                          }
                          placeholder="SHIPMENT"
                          required
                        />
                      </div>
                    </div>
                    <div>
                      <Label>Minimum Charge (optional)</Label>
                      <Input
                        value={charge.min_charge_fcy || ""}
                        onChange={(event) =>
                          handleChargeFieldChange(
                            index,
                            "min_charge_fcy",
                            event.target.value,
                          )
                        }
                        placeholder="0.00"
                      />
                    </div>
                    <div>
                      <Label>Valid Until (optional)</Label>
                      <Input
                        type="date"
                        value={charge.valid_until || ""}
                        onChange={(event) =>
                          handleChargeFieldChange(
                            index,
                            "valid_until",
                            event.target.value,
                          )
                        }
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <PageActionBar>
              <PageCancelButton
                href={returnTo || `/quotes/${quotationId}`}
                isDirty={isDirty}
                confirmMessage="Discard these manual rate changes?"
                confirmLeave={confirmLeave}
                disabled={isSubmitting}
              />
              <Button
                type="button"
                variant="secondary"
                onClick={handleAddCharge}
                disabled={!componentOptions.length || isSubmitting}
              >
                <Plus className="mr-2 h-4 w-4" />
                Add Manual Rate
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting || !canSubmit}
                loading={isSubmitting}
                loadingText="Saving version..."
              >
                Save Version
              </Button>
            </PageActionBar>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
