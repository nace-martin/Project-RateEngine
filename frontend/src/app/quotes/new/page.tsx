"use client";

import { useState, useEffect, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useFieldArray, useWatch, type Resolver, type FieldErrors } from "react-hook-form";
import { Trash2, Loader2 } from "lucide-react";
import type {
  Contact,
  CompanySearchResult,
  LocationSearchResult,
  V3QuoteComputeRequest,
} from "@/lib/types";
import { getContactsForCompany, computeQuoteV3, validateSpotScope, evaluateSpotTrigger } from "@/lib/api";
import { useSpotMode } from "@/hooks/use-spot-mode";
import { SpotModeBanner, OutOfScopeBanner } from "@/components/spot";
import type { SPECommodity, TriggerResult } from "@/lib/spot-types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  quoteFormSchemaV3,
  type QuoteFormSchemaV3,
  V3_MODES,
  V3_INCOTERMS,
  V3_PAYMENT_TERMS,
  V3_SERVICE_SCOPES,
  V3_LOCATION_TYPES,
  V3_CARGO_TYPES,
  getValidIncoterms,
  getDefaultIncoterm,
} from "@/lib/schemas/quoteSchema";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import LocationSearchCombobox from "@/components/LocationSearchCombobox";
import CompanySearchCombobox from "@/components/CompanySearchCombobox";
import { useAuth } from "@/context/auth-context";
import { useRouter } from "next/navigation";
import { MissingRatesModal } from "@/components/pricing/MissingRatesModal";

const buildQuoteComputePayload = (
  data: QuoteFormSchemaV3,
  spotRates?: {
    carrierSpotRatePgk: string;
    agentDestChargesFcy: string;
    agentCurrency: string;
    isAllIn?: boolean;
  },
  existingQuoteId?: string | null
): V3QuoteComputeRequest => {
  const payload: V3QuoteComputeRequest = {
    quote_id: existingQuoteId || undefined,
    customer_id: data.customer_id,
    contact_id: data.contact_id,
    mode: data.mode,
    incoterm: data.incoterm,
    payment_term: data.payment_term,
    service_scope: data.service_scope,
    origin_location_id: data.origin_location_id,
    destination_location_id: data.destination_location_id,
    dimensions: data.dimensions.map((dimension) => ({
      pieces: dimension.pieces,
      length_cm: dimension.length_cm,
      width_cm: dimension.width_cm,
      height_cm: dimension.height_cm,
      gross_weight_kg: dimension.gross_weight_kg,
    })),
    overrides: data.overrides?.map((override) => ({
      service_component_id: override.service_component_id,
      cost_fcy: override.cost_fcy,
      currency: override.currency,
      unit: override.unit,
      min_charge_fcy: override.min_charge_fcy,
    })),
    is_dangerous_goods: data.cargo_type === V3_CARGO_TYPES.DANGEROUS_GOODS,
    output_currency: data.output_currency || undefined,
  };

  if (spotRates) {
    const spots: Record<string, unknown> = {};
    if (spotRates.carrierSpotRatePgk) {
      spots['FRT_AIR_EXP'] = {
        amount: spotRates.carrierSpotRatePgk,
        currency: 'PGK',
        is_all_in: spotRates.isAllIn
      };
    }
    if (spotRates.agentDestChargesFcy) {
      spots['DST_CHARGES'] = {
        amount: spotRates.agentDestChargesFcy,
        currency: spotRates.agentCurrency || 'USD'
      };
    }
    if (Object.keys(spots).length > 0) {
      payload.spot_rates = spots;
    }
  }

  return payload;
};

export default function NewQuotePage() {
  const { user } = useAuth();
  const router = useRouter();
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<CompanySearchResult | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [isLoadingContacts, setIsLoadingContacts] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [originLocation, setOriginLocation] = useState<LocationSearchResult | null>(null);
  const [destinationLocation, setDestinationLocation] = useState<LocationSearchResult | null>(null);

  // Spot Rate State
  const [spotRates, setSpotRates] = useState({
    carrierSpotRatePgk: "",
    agentDestChargesFcy: "",
    agentCurrency: "USD",
    isAllIn: false
  });
  const [missingRates, setMissingRates] = useState({
    carrier: false,
    agent: false
  });
  const [showMissingRatesModal, setShowMissingRatesModal] = useState(false);
  const [pendingQuoteId, setPendingQuoteId] = useState<string | null>(null);
  const [pendingFormData, setPendingFormData] = useState<QuoteFormSchemaV3 | null>(null);

  // SPOT Mode State
  const { state: spotState, actions: spotActions } = useSpotMode();
  const [showSpotBanner, setShowSpotBanner] = useState(false);
  const [spotTriggerResult, setSpotTriggerResult] = useState<TriggerResult | null>(null);

  const form = useForm<QuoteFormSchemaV3>({
    resolver: zodResolver(quoteFormSchemaV3) as Resolver<QuoteFormSchemaV3>,
    mode: "onChange",
    reValidateMode: "onChange",
    defaultValues: {
      customer_id: "",
      contact_id: "",
      mode: "AIR",
      incoterm: "EXW",
      payment_term: "PREPAID",
      service_scope: V3_SERVICE_SCOPES.A2A,
      origin_airport: "",
      destination_airport: "",
      origin_location_type: V3_LOCATION_TYPES.AIRPORT,
      origin_location_id: "",
      destination_location_type: V3_LOCATION_TYPES.AIRPORT,
      destination_location_id: "",
      cargo_type: V3_CARGO_TYPES.GENERAL,
      dimensions: [{
        pieces: 1,
        length_cm: "",
        width_cm: "",
        height_cm: "",
        gross_weight_kg: "",
        package_type: "Box",
      }],
    },
  });
  const { isValid, isDirty } = form.formState;
  const canCalculateQuote = isDirty && isValid;

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "dimensions",
  });

  // Live Cargo Metrics Calculation - useWatch for proper reactivity
  const watchedDimensions = useWatch({
    control: form.control,
    name: "dimensions",
  });

  const cargoMetrics = useMemo(() => {
    if (!watchedDimensions || watchedDimensions.length === 0) {
      return { pieces: 0, actualWeight: 0, volumetricWeight: 0, chargeableWeight: 0 };
    }

    let totalPieces = 0;
    let totalActual = 0;
    let totalVolumetric = 0;

    for (const dim of watchedDimensions) {
      const pcs = parseInt(String(dim.pieces), 10) || 0;
      const l = parseFloat(String(dim.length_cm)) || 0;
      const w = parseFloat(String(dim.width_cm)) || 0;
      const h = parseFloat(String(dim.height_cm)) || 0;
      const kg = parseFloat(String(dim.gross_weight_kg)) || 0;

      totalPieces += pcs;
      totalActual += kg;
      totalVolumetric += (l * w * h / 6000) * pcs;
    }

    // Chargeable weight is max of actual vs volumetric, rounded UP to next kg
    const chargeableRaw = Math.max(totalActual, totalVolumetric);
    const chargeableRounded = chargeableRaw > 0 ? Math.ceil(chargeableRaw) : 0;

    return {
      pieces: totalPieces,
      actualWeight: Math.round(totalActual * 10) / 10,
      volumetricWeight: Math.round(totalVolumetric * 10) / 10,
      chargeableWeight: chargeableRounded,
    };
  }, [watchedDimensions]);

  const originLocationId = form.watch("origin_location_id");
  const destinationLocationId = form.watch("destination_location_id");

  useEffect(() => {
    if (!originLocationId) {
      setOriginLocation(null);
    }
  }, [originLocationId]);

  useEffect(() => {
    if (!destinationLocationId) {
      setDestinationLocation(null);
    }
  }, [destinationLocationId]);

  const setLocationFields = (
    kind: "origin" | "destination",
    location: LocationSearchResult | null,
    onLocationIdChange: (value: string) => void,
  ) => {
    const locationId = location?.id ?? "";
    const airportCode = (location?.code ?? "").toUpperCase();

    onLocationIdChange(locationId);

    if (kind === "origin") {
      form.setValue("origin_location_type", V3_LOCATION_TYPES.AIRPORT, {
        shouldDirty: true,
        shouldValidate: true,
      });
      form.setValue("origin_airport", airportCode, {
        shouldDirty: true,
        shouldValidate: true,
      });
    } else {
      form.setValue("destination_location_type", V3_LOCATION_TYPES.AIRPORT, {
        shouldDirty: true,
        shouldValidate: true,
      });
      form.setValue("destination_airport", airportCode, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  };

  // Determine if this is an Import (destination is PNG)
  const isImport = destinationLocation?.country_code === 'PG';

  // Watch form fields for incoterm filtering
  const serviceScope = form.watch('service_scope');
  const paymentTerm = form.watch('payment_term');
  const currentIncoterm = form.watch('incoterm');

  // Get valid incoterms based on direction, scope, and payment term
  const validIncoterms = useMemo(() => {
    return getValidIncoterms(isImport, serviceScope, paymentTerm);
  }, [isImport, serviceScope, paymentTerm]);

  // Auto-select correct incoterm when scope, direction, or payment term changes
  useEffect(() => {
    if (!validIncoterms.includes(currentIncoterm)) {
      const defaultIncoterm = getDefaultIncoterm(isImport, serviceScope, paymentTerm);
      form.setValue('incoterm', defaultIncoterm as keyof typeof V3_INCOTERMS, {
        shouldValidate: true,
      });
    }
  }, [validIncoterms, currentIncoterm, isImport, serviceScope, paymentTerm, form]);

  useEffect(() => {
    const fetchContacts = async (customerId: string) => {
      if (!user || !customerId) return;
      setIsLoadingContacts(true);
      setContacts([]);
      try {
        const fetchedContacts = await getContactsForCompany(customerId);
        setContacts(fetchedContacts);
      } catch (error: unknown) {
        console.error("Error fetching contacts:", error);
        setApiError("Failed to fetch contacts.");
      } finally {
        setIsLoadingContacts(false);
      }
    };

    if (selectedCustomerId) {
      fetchContacts(selectedCustomerId);
    }
  }, [selectedCustomerId, user]);

  // Reset any pending quote linkage when the customer changes
  useEffect(() => {
    setPendingQuoteId(null);
  }, [selectedCustomerId]);

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

  // Handler for modal spot rate submission
  const handleMissingRatesSubmit = async (newSpotRates: {
    carrierSpotRatePgk: string;
    agentDestChargesFcy: string;
    agentCurrency: string;
    isAllIn: boolean;
  }) => {
    if (!pendingFormData || !user) return;

    setIsSubmitting(true);
    setSpotRates(newSpotRates);
    setShowMissingRatesModal(false);
    setApiError(null);

    try {
      const payload = buildQuoteComputePayload(pendingFormData, newSpotRates, pendingQuoteId);
      console.log('Recalculating with spot rates:', JSON.stringify(payload.spot_rates, null, 2));

      const response = await computeQuoteV3(payload);
      console.log('Recalculate response:', response.id, 'has_missing_rates:', response.latest_version.totals.has_missing_rates);

      // Check if still missing rates
      if (response.latest_version.totals.has_missing_rates) {
        // Update pending quote ID in case it changed
        setPendingQuoteId(response.id);

        // Recheck which rates are still missing
        const lines = response.latest_version.lines;
        const stillMissingCarrier = lines.some(l => l.service_component.code === 'FRT_AIR_EXP' && l.is_rate_missing);
        const destComponents = ['DST-DELIV-STD', 'DST-CLEAR-CUS', 'DST-HANDL-STD', 'DST-DOC-IMP', 'DST_CHARGES'];
        const stillMissingAgent = lines.some(l => destComponents.includes(l.service_component.code) && l.is_rate_missing);

        setMissingRates({ carrier: stillMissingCarrier, agent: stillMissingAgent });
        setShowMissingRatesModal(true);
        setApiError("Some rates are still missing. Please verify your entries.");
        setIsSubmitting(false);
        return;
      }

      // Success! Clean up and redirect
      setPendingQuoteId(null);
      setPendingFormData(null);
      setMissingRates({ carrier: false, agent: false });
      router.push(`/quotes/${response.id}`);
    } catch (error: unknown) {
      console.error("API Error during recalculation:", error);
      const message = error instanceof Error ? error.message : "An unexpected error occurred.";
      setApiError(message);
      // Reopen modal so user can try again
      setShowMissingRatesModal(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Map frontend cargo type to SPE commodity code
  const mapCargoToSPECommodity = (cargoType: string): SPECommodity => {
    switch (cargoType) {
      case 'Dangerous Goods': return 'DG';
      case 'Perishable / Cold Chain': return 'PER';
      case 'Live Animals': return 'AVI';
      case 'Valuable / High-Value': return 'HVC';
      case 'Oversized / OOG': return 'OOG';
      case 'General Cargo':
      default: return 'GCR';
    }
  };

  async function onSubmit(data: QuoteFormSchemaV3) {
    setIsSubmitting(true);
    setApiError(null);
    setMissingRates({ carrier: false, agent: false });
    setShowSpotBanner(false);
    setSpotTriggerResult(null);

    if (!user) {
      setApiError("Authentication token not available. Please log in.");
      setIsSubmitting(false);
      return;
    }

    // Get country codes from locations
    const originCountry = originLocation?.country_code || '';
    const destCountry = destinationLocation?.country_code || '';

    // SPOT Mode Step 1: Validate scope (PNG only)
    try {
      const scopeResult = await validateSpotScope({
        origin_country: originCountry,
        destination_country: destCountry,
      });

      if (!scopeResult.is_valid) {
        // Out of scope - hard block
        setApiError(scopeResult.error || "Shipment out of scope - only PNG routes supported");
        setIsSubmitting(false);
        return;
      }
    } catch (error) {
      console.error("Scope validation error:", error);
      // If scope validation fails, continue with normal flow
      // (backend will catch any scope issues)
    }

    // SPOT Mode Step 2: Evaluate trigger
    try {
      const commodity = mapCargoToSPECommodity(data.cargo_type);
      const triggerResult = await evaluateSpotTrigger({
        origin_country: originCountry,
        destination_country: destCountry,
        commodity,
        origin_airport: data.origin_airport,
        destination_airport: data.destination_airport,
        has_valid_buy_rate: true, // Will be determined by pricing attempt
      });

      if (triggerResult.is_spot_required && triggerResult.trigger) {
        // SPOT mode required - show banner
        setShowSpotBanner(true);
        setSpotTriggerResult(triggerResult.trigger);
        setIsSubmitting(false);
        return;
      }
    } catch (error) {
      console.error("Trigger evaluation error:", error);
      // If trigger eval fails, continue with normal flow
    }

    // Normal pricing flow
    try {
      // Always include spot rates if they are populated
      const payload = buildQuoteComputePayload(data, spotRates, pendingQuoteId);
      const response = await computeQuoteV3(payload);
      console.log('Quote compute response:', response);

      // Check for missing rates (with null-safe access)
      const hasMissingRates = response.latest_version?.totals?.has_missing_rates ?? false;
      if (hasMissingRates) {
        const lines = response.latest_version?.lines ?? [];
        let missingCarrier = false;
        let missingAgent = false;

        // Check for missing carrier rates (FRT_AIR_EXP)
        if (lines.some(l => l.service_component.code === 'FRT_AIR_EXP' && l.is_rate_missing)) {
          missingCarrier = true;
        }

        // Check for missing agent rates (Destination Charges)
        const destComponents = ['DST-DELIV-STD', 'DST-CLEAR-CUS', 'DST-HANDL-STD', 'DST-DOC-IMP', 'DST_CHARGES'];
        if (lines.some(l => destComponents.includes(l.service_component.code) && l.is_rate_missing)) {
          missingAgent = true;
        }

        if (missingCarrier || missingAgent) {
          setMissingRates({ carrier: missingCarrier, agent: missingAgent });
          setPendingQuoteId(response.id);
          setPendingFormData(data);
          setShowMissingRatesModal(true);
          setIsSubmitting(false);
          return;
        }
      }

      console.log('Redirecting to quote:', response.id);
      setPendingQuoteId(null);
      router.push(`/quotes/${response.id}`);
    } catch (error: unknown) {
      console.error("API Error:", error);
      const message =
        error instanceof Error && error.message
          ? error.message
          : "An unexpected error occurred.";
      setApiError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  const onInvalid = (errors: FieldErrors<QuoteFormSchemaV3>) => {
    console.error("Form validation errors:", JSON.stringify(errors, null, 2));
    console.log("Current form values:", form.getValues());

    const firstErrorKey = Object.keys(errors)[0];

    // Helper to find the first message in a nested error object
    const getErrorMessage = (error: unknown): string | null => {
      if (!error) return null;
      if (typeof error === 'string') return error;

      if (typeof error === 'object' && error !== null) {
        // Check for 'message' property safely
        const hasMessage = 'message' in error && typeof (error as Record<string, unknown>).message === 'string';
        if (hasMessage) {
          return (error as Record<string, unknown>).message as string;
        }

        // Check for 'root' property safely
        const hasRoot = 'root' in error;
        if (hasRoot) {
          return getErrorMessage((error as Record<string, unknown>).root);
        }

        // If it's an array or object, try to find the first child with a message
        for (const key in error) {
          const childMsg = getErrorMessage((error as Record<string, unknown>)[key]);
          if (childMsg) return childMsg;
        }
      }
      return null;
    };

    const errorMessage = getErrorMessage(errors) || "Please check all required fields.";

    setApiError(`Validation Error: ${errorMessage}`);

    // Attempt to scroll to the error
    if (firstErrorKey) {
      const errorElement = document.querySelector(`[name="${firstErrorKey}"]`);
      if (errorElement) {
        errorElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        (errorElement as HTMLElement).focus();
      } else {
        // Fallback for fields that might not map directly to a name attribute (e.g. dimensions root)
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <div className="container mx-auto max-w-5xl p-4 pb-32">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold">New Quote</h1>
          </div>

          {apiError && !missingRates.carrier && !missingRates.agent && (
            <Alert variant="destructive">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{apiError}</AlertDescription>
            </Alert>
          )}

          {/* SPOT Mode Banner */}
          {showSpotBanner && spotTriggerResult && (
            <SpotModeBanner
              triggerResult={spotTriggerResult}
              onEnterSpotMode={() => {
                // TODO: Navigate to SPOT rate entry flow
                console.log('Entering SPOT mode');
                setShowSpotBanner(false);
              }}
              isLoading={isSubmitting}
            />
          )}

          {/* 1. Customer */}
          <Card>
            <CardHeader>
              <CardTitle>Customer</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="customer_id"
                render={({ field }) => (
                  <FormItem className="flex flex-col">
                    <FormLabel>Customer</FormLabel>
                    <CompanySearchCombobox
                      value={selectedCustomer}
                      onSelect={(company) => {
                        setSelectedCustomer(company);
                        const companyId = company?.id ?? null;
                        field.onChange(companyId ?? "");
                        setSelectedCustomerId(companyId);
                        setContacts([]);
                        form.resetField("contact_id");
                      }}
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="contact_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Contact</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value || ""}
                      disabled={!selectedCustomerId || isLoadingContacts}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue
                            placeholder={
                              isLoadingContacts
                                ? "Loading contacts..."
                                : !selectedCustomerId
                                  ? "Select customer first"
                                  : "Select a contact"
                            }
                          />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {isLoadingContacts ? (
                          <SelectItem value="loading" disabled>
                            Loading...
                          </SelectItem>
                        ) : contacts.length > 0 ? (
                          contacts.map((contact) => (
                            <SelectItem key={contact.id} value={contact.id}>
                              {contact.first_name} {contact.last_name} ({contact.email})
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-contacts" disabled>
                            {selectedCustomerId
                              ? "No contacts found"
                              : "Select customer first"}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* 2. Routing */}
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
                      onSelect={(selection) => {
                        setOriginLocation(selection);
                        setLocationFields("origin", selection, field.onChange);
                      }}
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
                      onSelect={(selection) => {
                        setDestinationLocation(selection);
                        setLocationFields("destination", selection, field.onChange);
                      }}
                    />
                    <FormDescription>Select any supported location (airport, port, city, or address).</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* 3. Shipment & Terms */}
          <Card>
            <CardHeader>
              <CardTitle>Shipment & Terms</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-3">
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
                        {Object.values(V3_MODES).map((mode) => (
                          <SelectItem key={mode} value={mode}>
                            {mode}
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
                        {validIncoterms.map((incoterm) => (
                          <SelectItem key={incoterm} value={incoterm}>
                            {incoterm}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {validIncoterms.length === 1 && isImport && serviceScope === 'A2D' && (
                      <FormDescription className="text-amber-600">
                        Import A2D quotes require DAP (Delivered at Place)
                      </FormDescription>
                    )}
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
                          <SelectValue placeholder="Select payment term" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {Object.values(V3_PAYMENT_TERMS).map((term) => (
                          <SelectItem key={term} value={term}>
                            {term}
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
                        {Object.values(V3_SERVICE_SCOPES).map((scope) => (
                          <SelectItem key={scope} value={scope}>
                            {scope}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>Door/Airport selection for pricing logic.</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Cargo Category (Moved from Other Details) */}
              <FormField
                control={form.control}
                name="cargo_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Cargo Category</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select category" />
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
            </CardContent>
          </Card>

          {/* 4. Cargo Dimensions */}
          <Card>
            <CardHeader>
              <CardTitle>Cargo Dimensions</CardTitle>
              <CardDescription>
                Provide at least one piece line with dimensions and weight.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {fields.map((fieldItem, index) => (
                <Card key={fieldItem.id}>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0">
                    <CardTitle className="text-base font-semibold">
                      Piece {index + 1}
                    </CardTitle>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(index)}
                      aria-label={`Remove piece ${index + 1}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.package_type`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Type</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Type" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                <SelectItem value="Box">Box</SelectItem>
                                <SelectItem value="Pallet">Pallet</SelectItem>
                                <SelectItem value="Crate">Crate</SelectItem>
                                <SelectItem value="Skid">Skid</SelectItem>
                                <SelectItem value="Drum">Drum</SelectItem>
                                <SelectItem value="Loose">Loose</SelectItem>
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.pieces`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Pieces</FormLabel>
                            <FormControl>
                              <Input type="number" min={1} {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.length_cm`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Length (cm)</FormLabel>
                            <FormControl>
                              <Input type="number" step="0.01" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.width_cm`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Width (cm)</FormLabel>
                            <FormControl>
                              <Input type="number" step="0.01" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.height_cm`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Height (cm)</FormLabel>
                            <FormControl>
                              <Input type="number" step="0.01" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.gross_weight_kg`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Weight (kg)</FormLabel>
                            <FormControl>
                              <Input type="number" step="0.01" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={addPieceLine}
              >
                Add Piece Line
              </Button>
              {form.formState.errors.dimensions?.root?.message && (
                <p className="text-sm font-medium text-destructive">
                  {form.formState.errors.dimensions.root.message}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Cargo Summary Display */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-gradient-to-r from-muted/30 to-muted/50 rounded-lg border">
            <div className="text-center">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Pieces</div>
              <div className="text-xl font-bold text-foreground tabular-nums">{cargoMetrics.pieces}</div>
            </div>
            <div className="text-center">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Actual</div>
              <div className="text-xl font-bold text-foreground tabular-nums">{cargoMetrics.actualWeight} kg</div>
            </div>
            <div className="text-center">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Volumetric</div>
              <div className="text-xl font-bold text-foreground tabular-nums">{cargoMetrics.volumetricWeight} kg</div>
            </div>
            <div className="text-center">
              <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Chargeable</div>
              <div className="text-2xl font-bold text-primary tabular-nums">{cargoMetrics.chargeableWeight} kg</div>
            </div>
          </div>

          {/* Sticky Footer */}
          <div className="fixed bottom-0 left-0 right-0 border-t bg-background p-4 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.1)] md:pl-64 z-50">
            <div className="container mx-auto flex max-w-5xl items-center justify-between">
              <div className="text-sm text-muted-foreground hidden md:block">
                {canCalculateQuote ? "Ready to calculate." : "Complete all required fields to calculate."}
              </div>
              <Button
                type="submit"
                size="lg"
                disabled={isSubmitting}
                className="w-full md:w-auto min-w-[200px] h-12 text-base font-semibold shadow-lg bg-gradient-to-r from-primary to-primary/80 hover:from-primary/90 hover:to-primary/70 transition-all"
              >
                {isSubmitting && <Loader2 className="mr-2 h-5 w-5 animate-spin" />}
                Calculate Quote
              </Button>
            </div>
          </div>

        </form>
      </Form>

      {/* Missing Rates Modal - Email template only */}
      <MissingRatesModal
        isOpen={showMissingRatesModal}
        onClose={() => {
          setShowMissingRatesModal(false);
          // Route to quote detail page if quote was already saved
          if (pendingQuoteId) {
            router.push(`/quotes/${pendingQuoteId}`);
          }
        }}
        onSubmit={() => {
          // Track that email was copied, then navigate to quote
          console.log('Email template copied for partner quote');
          setShowMissingRatesModal(false);
          if (pendingQuoteId) {
            router.push(`/quotes/${pendingQuoteId}`);
          }
        }}
        missingRates={missingRates}
        quoteId={pendingQuoteId}
        shipmentDetails={{
          origin: originLocation?.display_name || form.watch('origin_airport') || 'Origin',
          destination: destinationLocation?.display_name || form.watch('destination_airport') || 'Destination',
          originCountryCode: originLocation?.country_code,
          destinationCountryCode: destinationLocation?.country_code,
          mode: form.watch('mode'),
          pieces: cargoMetrics.pieces,
          weight: cargoMetrics.actualWeight,
          chargeableWeight: cargoMetrics.chargeableWeight,
          volumetricWeight: cargoMetrics.volumetricWeight,
          commodity: form.watch('cargo_type'),
          serviceScope: form.watch('service_scope'),
          incoterm: form.watch('incoterm'),
          dimensions: form.watch('dimensions'),
        }}
      />
    </div>
  );
}
