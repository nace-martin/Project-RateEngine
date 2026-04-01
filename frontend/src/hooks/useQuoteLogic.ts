import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, useWatch, Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { getContactsForCompany } from "@/lib/api/parties";
import { validateSpotScope, evaluateSpotTrigger, createSpotEnvelope } from "@/lib/api/spot";
import {
    calculateCargoMetrics,
} from "@/components/forms/quote-sections/quote-section-types";
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
import { Contact, CompanySearchResult, LocationSearchResult, User } from "@/lib/types";
import { SPECommodity } from "@/lib/spot-types";
import { useQuoteStore } from "@/store/useQuoteStore";

const EMPTY_CONTACTS: Contact[] = [];

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

const AIRPORT_COUNTRY_MAP: Record<string, string> = {
    POM: "PG",
    LAE: "PG",
    SIN: "SG",
    HKG: "HK",
    BNE: "AU",
    SYD: "AU",
    CNS: "AU",
    NAN: "FJ",
    HIR: "SB",
    VLI: "VU",
};

const resolveCountryCode = (
    location: LocationSearchResult | null,
    airportCode?: string,
): string => {
    const explicit = (location?.country_code || "").trim().toUpperCase();
    if (explicit) return explicit;

    const displayName = location?.display_name || "";
    const displayMatch = displayName.match(/,\s*([A-Z]{2})\s*$/i);
    if (displayMatch?.[1]) {
        return displayMatch[1].toUpperCase();
    }

    const code = (airportCode || location?.code || "").trim().toUpperCase();
    return AIRPORT_COUNTRY_MAP[code] || "OTHER";
};

interface UseQuoteLogicProps {
    defaultValues?: Partial<QuoteFormSchemaV3>;
    initialCustomer?: CompanySearchResult;
    initialContacts?: Contact[];
    initialOrigin?: LocationSearchResult;
    initialDestination?: LocationSearchResult;
    user?: User | null; // Auth user
    onSubmit: (data: QuoteFormSchemaV3) => Promise<void>;
    isEditMode?: boolean; // Skip SPOT validation when editing existing quotes
}

export function useQuoteLogic({
    defaultValues,
    initialCustomer,
    initialContacts = EMPTY_CONTACTS,
    initialOrigin,
    initialDestination,
    user,
    onSubmit,
    isEditMode = false,
}: UseQuoteLogicProps) {
    const router = useRouter();
    const [internalError, setInternalError] = useState<string | null>(null);
    const submitLockRef = useRef(false);
    const selectedCustomer = useQuoteStore((state) => state.selectedCustomer);
    const originLocation = useQuoteStore((state) => state.originLocation);
    const destinationLocation = useQuoteStore((state) => state.destinationLocation);
    const setContacts = useQuoteStore((state) => state.setContacts);
    const setIsLoadingContacts = useQuoteStore((state) => state.setIsLoadingContacts);
    const setSelectedCustomer = useQuoteStore((state) => state.setSelectedCustomer);
    const setOriginLocation = useQuoteStore((state) => state.setOriginLocation);
    const setDestinationLocation = useQuoteStore((state) => state.setDestinationLocation);
    const setSpotMode = useQuoteStore((state) => state.setSpotMode);

    const form = useForm<QuoteFormSchemaV3>({
        resolver: zodResolver(quoteFormSchemaV3) as Resolver<QuoteFormSchemaV3>,
        mode: "onChange",
        reValidateMode: "onChange",
        defaultValues: {
            customer_id: "",
            contact_id: "",
            mode: "AIR",
            incoterm: defaultValues?.incoterm,
            payment_term: defaultValues?.payment_term,
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

    useEffect(() => {
        setSelectedCustomer(initialCustomer || null);
        setContacts(initialContacts);
        setOriginLocation(initialOrigin || null);
        setDestinationLocation(initialDestination || null);
        setSpotMode(false);
    }, [
        initialContacts,
        initialCustomer,
        initialDestination,
        initialOrigin,
        setContacts,
        setDestinationLocation,
        setOriginLocation,
        setSelectedCustomer,
        setSpotMode,
    ]);

    const watchedDimensions = useWatch({
        control: form.control,
        name: "dimensions",
    });
    const selectedCustomerId = useWatch({
        control: form.control,
        name: "customer_id",
    });
    const serviceScope = useWatch({
        control: form.control,
        name: "service_scope",
    });
    const paymentTerm = useWatch({
        control: form.control,
        name: "payment_term",
    });
    const currentIncoterm = useWatch({
        control: form.control,
        name: "incoterm",
    });

    const cargoMetrics = useMemo(() => {
        return calculateCargoMetrics(watchedDimensions);
    }, [watchedDimensions]);

    // --- Side Effects & Derived State ---

    // Auto-update Incoterms
    const isImport = destinationLocation?.country_code === 'PG';
    const validIncoterms = useMemo(() => {
        return getValidIncoterms(isImport, serviceScope, paymentTerm);
    }, [isImport, serviceScope, paymentTerm]);

    useEffect(() => {
        if (!paymentTerm) {
            return;
        }

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
    }, [selectedCustomerId, setContacts, setIsLoadingContacts, user]);

    // --- Handlers ---

    const handleFormSubmit = async (data: QuoteFormSchemaV3) => {
        if (submitLockRef.current) return;

        submitLockRef.current = true;
        setInternalError(null);
        setSpotMode(false);

        try {
            if (!user) {
                setInternalError("Authentication token not available. Please log in.");
                return;
            }

            // Skip SPOT validation when editing existing quotes
            if (isEditMode) {
                await onSubmit(data);
                return;
            }

            const originCode = (data.origin_airport || originLocation?.code || '').toUpperCase();
            const destinationCode = (data.destination_airport || destinationLocation?.code || '').toUpperCase();
            const originCountry = resolveCountryCode(originLocation, originCode);
            const destCountry = resolveCountryCode(destinationLocation, destinationCode);

            try {
                // 1. Validate Scope
                const scopeResult = await validateSpotScope({
                    origin_country: originCountry,
                    destination_country: destCountry,
                    origin_code: originCode,
                    destination_code: destinationCode,
                });

                if (!scopeResult.is_valid) {
                    setInternalError(scopeResult.error || "Shipment out of scope - only PNG routes supported");
                    return;
                }

                // 2. Evaluate Trigger
                const commodity = mapCargoToSPECommodity(data.cargo_type);
                const paymentTermUpper: 'PREPAID' | 'COLLECT' =
                    data.payment_term === 'COLLECT' ? 'COLLECT' : 'PREPAID';
                const paymentTermLower: 'prepaid' | 'collect' =
                    paymentTermUpper === 'COLLECT' ? 'collect' : 'prepaid';
                const triggerResult = await evaluateSpotTrigger({
                    origin_country: originCountry,
                    destination_country: destCountry,
                    commodity,
                    origin_airport: originCode,
                    destination_airport: destinationCode,
                    has_valid_buy_rate: true,
                    service_scope: data.service_scope,
                    payment_term: paymentTermUpper,
                });

                if (triggerResult.is_spot_required && triggerResult.trigger) {
                    setSpotMode(true);
                    const spe = await createSpotEnvelope({
                        shipment_context: {
                            origin_country: originCountry,
                            destination_country: destCountry,
                            origin_code: originCode,
                            destination_code: destinationCode,
                            customer_name: selectedCustomer?.name || undefined,
                            commodity: commodity as SPECommodity,
                            total_weight_kg: cargoMetrics.chargeableWeight,
                            pieces: cargoMetrics.pieces,
                            service_scope: (data.service_scope || 'P2P').toLowerCase(),
                            payment_term: paymentTermLower,
                            missing_components: triggerResult.trigger?.missing_components,
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
                        origin_code: originCode,
                        dest_code: destinationCode,
                        customer_id: data.customer_id,
                        customer_name: selectedCustomer?.name || "",
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

            setSpotMode(false);
            await onSubmit(data);
        } finally {
            submitLockRef.current = false;
        }
    };

    return {
        form,
        cargoMetrics,
        internalError,
        handleFormSubmit,
        validIncoterms,
        setInternalError
    };
}
