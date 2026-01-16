"use client";

import { useState, useEffect, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useFieldArray, useWatch, type Resolver, type FieldErrors, type UseFormReturn } from "react-hook-form";
import { Trash2, Loader2 } from "lucide-react";
import type {
    Contact,
    CompanySearchResult,
    LocationSearchResult,
} from "@/lib/types";
import { getContactsForCompany, validateSpotScope, evaluateSpotTrigger, createSpotEnvelope } from "@/lib/api";
import type { SPECommodity } from "@/lib/spot-types";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
    quoteFormSchemaV3,
    type QuoteFormSchemaV3,
    V3_INCOTERMS,
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
import { CustomerSection } from "./sections/CustomerSection";
import { RoutingSection } from "./sections/RoutingSection";
import { ShipmentTermsSection } from "./sections/ShipmentTermsSection";
import { CargoDetailsSection } from "./sections/CargoDetailsSection";

export interface QuoteFormProps {
    defaultValues?: Partial<QuoteFormSchemaV3>;
    // Additional initial state for UI components that aren't strictly part of the form schema but needed for display
    initialCustomer?: CompanySearchResult;
    initialContacts?: Contact[];
    initialOrigin?: LocationSearchResult;
    initialDestination?: LocationSearchResult;
    onSubmit: (data: QuoteFormSchemaV3) => Promise<void>;
    isSubmitting?: boolean;
    serverError?: string | null;
}

export default function QuoteForm({
    defaultValues,
    initialCustomer,
    initialContacts = [],
    initialOrigin,
    initialDestination,
    onSubmit,
    isSubmitting = false,
    serverError = null,
}: QuoteFormProps) {
    const { user } = useAuth();
    const router = useRouter();

    // Local UI State
    const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(defaultValues?.customer_id || null);
    const [selectedCustomer, setSelectedCustomer] = useState<CompanySearchResult | null>(initialCustomer || null);
    const [contacts, setContacts] = useState<Contact[]>(initialContacts);
    const [isLoadingContacts, setIsLoadingContacts] = useState(false);
    const [internalError, setInternalError] = useState<string | null>(null);

    // Combine internal and external errors
    const apiError = serverError || internalError;

    const [originLocation, setOriginLocation] = useState<LocationSearchResult | null>(initialOrigin || null);
    const [destinationLocation, setDestinationLocation] = useState<LocationSearchResult | null>(initialDestination || null);

    // Spot/Missing Rates State
    // Note: These might be better lifted up if the parent needs to know, 
    // but for now they are tightly coupled to the form submission flow.
    const [missingRates, setMissingRates] = useState({ carrier: false, agent: false });
    // MissingRatesModal is handled by the parent in the original code, but effectively it's part of the "Submit" flow.
    // We will keep it here or lift it? The original code had it in the page. 
    // For `QuoteForm`, let's try to keep self-contained, BUT `MissingRatesModal` needs to re-trigger submission.
    // Actually, `MissingRatesModal` creates a task/linkage. It might be easier if `onSubmit` handles the flow, 
    // OR we expose a way to trigger the modal.
    // For simplicity: We will assume the PARENT handles the "Missing Rates" logic if it catches that specific response? 
    // No, the original logic had `onSubmit` doing the API call and THEN showing the modal.
    // To keep `QuoteForm` pure, `onSubmit` should just return the data. 
    // BUT the "Spot Trigger" logic redirects the router.

    // Refactor Decision: `QuoteForm` handles the UI and validation. 
    // The `onSubmit` prop should handle the API call. 
    // However, the "Spot Trigger" logic is pre-submission validation. We should keep that here.

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
            ...defaultValues,
        },
    });

    const { isValid, isDirty } = form.formState;

    const { fields, append, remove } = useFieldArray({
        control: form.control,
        name: "dimensions",
    });

    // Live Cargo Metrics
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
        if (!originLocationId) setOriginLocation(null);
    }, [originLocationId]);

    useEffect(() => {
        if (!destinationLocationId) setDestinationLocation(null);
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
            form.setValue("origin_location_type", V3_LOCATION_TYPES.AIRPORT, { shouldDirty: true, shouldValidate: true });
            form.setValue("origin_airport", airportCode, { shouldDirty: true, shouldValidate: true });
        } else {
            form.setValue("destination_location_type", V3_LOCATION_TYPES.AIRPORT, { shouldDirty: true, shouldValidate: true });
            form.setValue("destination_airport", airportCode, { shouldDirty: true, shouldValidate: true });
        }
    };

    const isImport = destinationLocation?.country_code === 'PG';
    const serviceScope = form.watch('service_scope');
    const paymentTerm = form.watch('payment_term');
    const currentIncoterm = form.watch('incoterm');

    const validIncoterms = useMemo(() => {
        return getValidIncoterms(isImport, serviceScope, paymentTerm);
    }, [isImport, serviceScope, paymentTerm]);

    useEffect(() => {
        if (!validIncoterms.includes(currentIncoterm)) {
            const defaultIncoterm = getDefaultIncoterm(isImport, serviceScope, paymentTerm);
            form.setValue('incoterm', defaultIncoterm as keyof typeof V3_INCOTERMS, { shouldValidate: true });
        }
    }, [validIncoterms, currentIncoterm, isImport, serviceScope, paymentTerm, form]);

    useEffect(() => {
        const fetchContacts = async (customerId: string) => {
            if (!user || !customerId) return;
            setIsLoadingContacts(true);
            try {
                const fetchedContacts = await getContactsForCompany(customerId);
                setContacts(fetchedContacts);
            } catch (error: unknown) {
                console.error("Error fetching contacts:", error);
            } finally {
                setIsLoadingContacts(false);
            }
        };

        // Auto-fetch if customer changes (and we aren't in the middle of initial hydration which is handled by props usually,
        // but here we just react to the state).
        if (selectedCustomerId) {
            // Avoid re-fetching if the contacts passed in props match the customer (optimization)
            // For now, simpler to just fetch to ensure freshness, unless contacts are already populated correctly?
            // To avoid infinite loops or overwriting initial data:
            // If initialContacts are provided and match the defaultValues.customer_id, we might not need to fetch immediately.
            // But for simplicity, we'll let it fetch or check if contacts are empty.
            if (contacts.length === 0 || (contacts.length > 0 && selectedCustomerId !== defaultValues?.customer_id)) {
                fetchContacts(selectedCustomerId);
            }
        } else {
            setContacts([]);
        }
    }, [selectedCustomerId, user]); // Removed defaultValues dependency to avoid loop

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

    const handleFormSubmit = async (data: QuoteFormSchemaV3) => {
        setInternalError(null);
        setMissingRates({ carrier: false, agent: false });

        if (!user) {
            setInternalError("Authentication token not available. Please log in.");
            return;
        }

        const originCountry = originLocation?.country_code || '';
        const destCountry = destinationLocation?.country_code || '';

        // SPOT Logic
        try {
            // 1. Validate Scope
            const scopeResult = await validateSpotScope({
                origin_country: originCountry,
                destination_country: destCountry,
            });

            if (!scopeResult.is_valid) {
                setInternalError(scopeResult.error || "Shipment out of scope - only PNG routes supported");
                return;
            }

            // 2. Evaluate Trigger
            const commodity = mapCargoToSPECommodity(data.cargo_type);
            const triggerResult = await evaluateSpotTrigger({
                origin_country: originCountry,
                destination_country: destCountry,
                commodity,
                origin_airport: data.origin_airport,
                destination_airport: data.destination_airport,
                has_valid_buy_rate: true,
                service_scope: data.service_scope,
            });

            if (triggerResult.is_spot_required && triggerResult.trigger) {
                const spe = await createSpotEnvelope({
                    shipment_context: {
                        origin_country: originCountry,
                        destination_country: destCountry,
                        origin_code: data.origin_airport || '',
                        destination_code: data.destination_airport || '',
                        commodity: commodity as SPECommodity,
                        total_weight_kg: cargoMetrics.chargeableWeight,
                        pieces: cargoMetrics.pieces,
                        service_scope: (data.service_scope || 'P2P').toLowerCase(),
                    },
                    charges: [],
                    trigger_code: triggerResult.trigger.code,
                    trigger_text: triggerResult.trigger.text,
                    conditions: { rate_validity_hours: 72 }
                });

                if (spe) {
                    const shipmentType = originCountry === 'PG' && destCountry === 'PG' ? 'DOMESTIC' : (originCountry === 'PG' ? 'EXPORT' : 'IMPORT');
                    const params = new URLSearchParams({
                        origin_country: originCountry,
                        dest_country: destCountry,
                        origin_code: data.origin_airport || '',
                        dest_code: data.destination_airport || '',
                        commodity,
                        weight: String(cargoMetrics.chargeableWeight),
                        pieces: String(cargoMetrics.pieces),
                        trigger_code: triggerResult.trigger.code,
                        trigger_text: triggerResult.trigger.text,
                        service_scope: data.service_scope,
                        payment_term: data.payment_term,
                        output_currency: data.output_currency || 'PGK',
                        shipment_type: shipmentType,
                    });
                    if (triggerResult.trigger?.missing_components && triggerResult.trigger.missing_components.length > 0) {
                        params.append('missing_components', triggerResult.trigger.missing_components.join(','));
                    }
                    router.push(`/quotes/spot/${spe.id}?${params.toString()}`);
                    return; // Stop here, we redirected
                }
            }
        } catch (e) {
            console.error("Spot/Trigger logic error", e);
            // Continue to normal submit on error? Or block?
            // Originally we continued.
        }

        // Call Parent Submit
        await onSubmit(data);
    };

    const onInvalid = (errors: FieldErrors<QuoteFormSchemaV3>) => {
        // Error handling logic
        const firstErrorKey = Object.keys(errors)[0];
        const getErrorMessage = (error: any): string | null => {
            if (!error) return null;
            if (typeof error === 'string') return error;
            if (error.message) return error.message;
            if (error.root) return getErrorMessage(error.root);
            return null;
        };
        const errorMessage = getErrorMessage(errors) || "Please check required fields.";
        setInternalError(`Validation Error: ${errorMessage}`);

        if (firstErrorKey) {
            const el = document.querySelector(`[name="${firstErrorKey}"]`);
            el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            (el as HTMLElement)?.focus();
        } else {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        }
    };



    // ... (keep existing imports up to Card/Select/Input etc which might be unused now but acceptable to leave or remove if unused)
    // Ideally I should clean up unused imports too, but let's focus on the replacement first.

    // ... inside component

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(handleFormSubmit, onInvalid)} className="space-y-6">
                <div className="flex items-center justify-between">
                    <h1 className="text-3xl font-bold">
                        {defaultValues?.quote_id ? "Edit Quote" : "New Quote"}
                    </h1>
                </div>

                {apiError && (
                    <Alert variant="destructive">
                        <AlertTitle>Error</AlertTitle>
                        <AlertDescription>{apiError}</AlertDescription>
                    </Alert>
                )}

                {/* 1. Customer */}
                <CustomerSection
                    form={form}
                    contacts={contacts}
                    isLoadingContacts={isLoadingContacts}
                    selectedCustomerId={selectedCustomerId}
                    selectedCustomer={selectedCustomer}
                    onCustomerSelect={(company) => {
                        setSelectedCustomer(company);
                        const companyId = company?.id ?? null;
                        form.setValue("customer_id", companyId ?? "", { shouldDirty: true, shouldValidate: true });
                        setSelectedCustomerId(companyId);
                        setContacts([]);
                        if (companyId !== defaultValues?.customer_id) {
                            form.setValue("contact_id", "", { shouldValidate: true });
                        }
                    }}
                />

                {/* 2. Routing */}
                <RoutingSection
                    form={form}
                    originLocation={originLocation}
                    destinationLocation={destinationLocation}
                    onOriginSelect={(selection) => {
                        setOriginLocation(selection);
                        setLocationFields("origin", selection, (value) => form.setValue("origin_location_id", value, { shouldDirty: true, shouldValidate: true }));
                    }}
                    onDestinationSelect={(selection) => {
                        setDestinationLocation(selection);
                        setLocationFields("destination", selection, (value) => form.setValue("destination_location_id", value, { shouldDirty: true, shouldValidate: true }));
                    }}
                />

                {/* 3. Shipment & Terms */}
                <ShipmentTermsSection
                    form={form}
                    validIncoterms={validIncoterms}
                />

                {/* 4. Cargo Details */}
                <CargoDetailsSection
                    form={form}
                    fields={fields}
                    append={append}
                    remove={remove}
                    cargoMetrics={cargoMetrics}
                />

                <div className="flex justify-end gap-4 pb-20">
                    <Button type="button" variant="outline" onClick={() => router.back()}>
                        Cancel
                    </Button>
                    <Button type="submit" size="lg" disabled={isSubmitting || !isValid}>
                        {isSubmitting ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Calculating...
                            </>
                        ) : (
                            "Calculate Quote"
                        )}
                    </Button>
                </div>

            </form>
        </Form>
    );
}
