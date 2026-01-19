import { useState, useEffect, useMemo } from "react";
import { useForm, useFieldArray, useWatch, UseFormReturn, Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { getContactsForCompany, validateSpotScope, evaluateSpotTrigger, createSpotEnvelope } from "@/lib/api";
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
import { Contact, CompanySearchResult, LocationSearchResult } from "@/lib/types";
import { SPECommodity } from "@/lib/spot-types";

// Helper to map cargo type to commodity code
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

interface UseQuoteLogicProps {
    defaultValues?: Partial<QuoteFormSchemaV3>;
    initialCustomer?: CompanySearchResult;
    initialContacts?: Contact[];
    initialOrigin?: LocationSearchResult;
    initialDestination?: LocationSearchResult;
    user?: any; // Auth user
    onSubmit: (data: QuoteFormSchemaV3) => Promise<void>;
    isEditMode?: boolean; // Skip SPOT validation when editing existing quotes
}

export function useQuoteLogic({
    defaultValues,
    initialCustomer,
    initialContacts = [],
    initialOrigin,
    initialDestination,
    user,
    onSubmit,
    isEditMode = false,
}: UseQuoteLogicProps) {
    const router = useRouter();
    const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(defaultValues?.customer_id || null);
    const [selectedCustomer, setSelectedCustomer] = useState<CompanySearchResult | null>(initialCustomer || null);
    const [contacts, setContacts] = useState<Contact[]>(initialContacts);
    const [isLoadingContacts, setIsLoadingContacts] = useState(false);
    const [internalError, setInternalError] = useState<string | null>(null);
    const [originLocation, setOriginLocation] = useState<LocationSearchResult | null>(initialOrigin || null);
    const [destinationLocation, setDestinationLocation] = useState<LocationSearchResult | null>(initialDestination || null);

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

    const { fields, append, remove } = useFieldArray({
        control: form.control,
        name: "dimensions",
    });

    // --- Metrics Calculation ---
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

    // --- Side Effects & Derived State ---

    // Auto-update Incoterms
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

    // Fetch Contacts
    useEffect(() => {
        let isActive = true;

        const fetchContacts = async (customerId: string) => {
            if (!user || !customerId) {
                if (isActive) setContacts([]);
                return;
            }

            setIsLoadingContacts(true);
            try {
                const fetchedContacts = await getContactsForCompany(customerId);
                if (isActive) {
                    setContacts(fetchedContacts);
                }
            } catch (error: unknown) {
                console.error("Error fetching contacts:", error);
                if (isActive) setContacts([]);
            } finally {
                if (isActive) setIsLoadingContacts(false);
            }
        };

        if (selectedCustomerId) {
            fetchContacts(selectedCustomerId);
        } else {
            setContacts([]);
        }

        return () => {
            isActive = false;
        };
    }, [selectedCustomerId, user]);

    // --- Handlers ---

    const handleFormSubmit = async (data: QuoteFormSchemaV3) => {
        setInternalError(null);

        if (!user) {
            setInternalError("Authentication token not available. Please log in.");
            return;
        }

        // Skip SPOT validation when editing existing quotes
        if (isEditMode) {
            await onSubmit(data);
            return;
        }

        const originCountry = originLocation?.country_code || '';
        const destCountry = destinationLocation?.country_code || '';

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
                    return;
                }
            }
        } catch (e) {
            console.error("Spot/Trigger logic error", e);
        }

        await onSubmit(data);
    };

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

    return {
        form,
        fields,
        append,
        remove,
        cargoMetrics,
        internalError,
        contacts,
        isLoadingContacts,
        selectedCustomer,
        setSelectedCustomer,
        selectedCustomerId,
        setSelectedCustomerId,
        originLocation,
        setOriginLocation,
        destinationLocation,
        setDestinationLocation,
        handleFormSubmit,
        setLocationFields,
        validIncoterms,
        setInternalError
    };
}
