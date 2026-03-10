"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "@/context/auth-context";
import { useRouter } from "next/navigation";
import { getQuoteV3, computeQuoteV3, getContactsForCompany } from "@/lib/api";
import { type QuoteFormSchemaV3, V3_LOCATION_TYPES, V3_CARGO_TYPES } from "@/lib/schemas/quoteSchema";
import { V3QuoteComputeRequest, CompanySearchResult, LocationSearchResult, Contact, QuoteContactRef, QuoteCustomerRef, V3DimensionInput } from "@/lib/types";
import QuoteForm from "@/components/forms/QuoteForm";
import { MissingRatesModal } from "@/components/pricing/MissingRatesModal";
import { Loader2 } from "lucide-react";
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

// Reusing the payload builder - ideally this should be a shared utility
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
        is_dangerous_goods: data.cargo_type === 'Dangerous Goods',
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

export default function EditQuotePage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    const { user } = useAuth();
    const router = useRouter();

    const [isLoading, setIsLoading] = useState(true);
    const [initialData, setInitialData] = useState<Partial<QuoteFormSchemaV3> | null>(null);

    // Hydrated State for Form UI
    const [initialCustomer, setInitialCustomer] = useState<CompanySearchResult | undefined>(undefined);
    const [initialContacts, setInitialContacts] = useState<Contact[]>([]);
    const [initialOrigin, setInitialOrigin] = useState<LocationSearchResult | undefined>(undefined);
    const [initialDestination, setInitialDestination] = useState<LocationSearchResult | undefined>(undefined);

    const [isSubmitting, setIsSubmitting] = useState(false);
    const [apiError, setApiError] = useState<string | null>(null);

    // Missing Rates State
    const [missingRates, setMissingRates] = useState({ carrier: false, agent: false });
    const [showMissingRatesModal, setShowMissingRatesModal] = useState(false);

    useEffect(() => {
        const loadQuote = async () => {
            try {
                const quote = await getQuoteV3(id);
                if (quote.is_archived) {
                    const status = String(quote.status || '').toUpperCase();
                    const message = (status === 'DRAFT' || status === 'INCOMPLETE')
                        ? "This draft was deleted and can no longer be edited."
                        : "This quote is archived and read-only.";
                    setApiError(message);
                    return;
                }
                const payload =
                    (quote.latest_version?.payload_json as Record<string, unknown> | undefined)
                    ?? (quote.request_details_json as Record<string, unknown> | undefined);
                if (!payload) throw new Error("No payload found on quote");

                const shipmentPayload = (
                    payload.shipment && typeof payload.shipment === "object"
                        ? (payload.shipment as Record<string, unknown>)
                        : undefined
                );

                // 1. Prepare Initial Form Data
                let dimensions = [{
                    pieces: 1,
                    length_cm: "",
                    width_cm: "",
                    height_cm: "",
                    gross_weight_kg: "",
                    package_type: "Box",
                }];

                const rawDimensions = Array.isArray(payload.dimensions)
                    ? (payload.dimensions as V3DimensionInput[])
                    : Array.isArray(shipmentPayload?.pieces)
                        ? (shipmentPayload.pieces as V3DimensionInput[])
                        : [];

                if (rawDimensions.length > 0) {
                    dimensions = rawDimensions.map((d: V3DimensionInput) => ({
                        pieces: d.pieces,
                        length_cm: String(d.length_cm),
                        width_cm: String(d.width_cm),
                        height_cm: String(d.height_cm),
                        gross_weight_kg: String(d.gross_weight_kg),
                        package_type: "Box",
                    }));
                }

                // Helper to extract airport code from location string (format: "CODE - Name")
                const extractAirportCode = (locationStr: string | undefined | null): string => {
                    if (!locationStr) return "";
                    // Try to extract code from "CODE - Name" format
                    const match = locationStr.match(/^([A-Z]{3})\s*-/);
                    if (match) return match[1];
                    // Fallback: if it's already just a 3-letter code
                    if (/^[A-Z]{3}$/.test(locationStr.trim())) return locationStr.trim();
                    return "";
                };

                // Extract airport codes from API response
                const originAirportCode = extractAirportCode(quote.origin_location as string);
                const destinationAirportCode = extractAirportCode(quote.destination_location as string);

                const customerId = String(payload.customer_id || "");
                const contactId = String(
                    payload.contact_id
                    || (quote.contact as QuoteContactRef)?.id
                    || ""
                );
                const originLocationId = String(
                    payload.origin_location_id
                    || ((shipmentPayload?.origin_location as Record<string, unknown> | undefined)?.id ?? "")
                );
                const destinationLocationId = String(
                    payload.destination_location_id
                    || ((shipmentPayload?.destination_location as Record<string, unknown> | undefined)?.id ?? "")
                );
                const mode = String(payload.mode || shipmentPayload?.mode || "AIR");
                const incoterm = String(payload.incoterm || shipmentPayload?.incoterm || "EXW");
                const paymentTerm = String(payload.payment_term || shipmentPayload?.payment_term || "PREPAID");
                const serviceScope = String(payload.service_scope || shipmentPayload?.service_scope || "A2A");
                const isDangerousGoods = Boolean(
                    payload.is_dangerous_goods
                    ?? shipmentPayload?.is_dangerous_goods
                );

                const formData: Partial<QuoteFormSchemaV3> = {
                    quote_id: quote.id, // Important for tracking updates
                    customer_id: customerId,
                    contact_id: contactId,
                    mode: (mode as QuoteFormSchemaV3['mode']) || "AIR",
                    incoterm: (incoterm as QuoteFormSchemaV3['incoterm']) || "EXW",
                    payment_term: (paymentTerm as QuoteFormSchemaV3['payment_term']) || "PREPAID",
                    service_scope: (serviceScope as QuoteFormSchemaV3['service_scope']) || "A2A",
                    origin_airport: originAirportCode,
                    destination_airport: destinationAirportCode,
                    origin_location_id: originLocationId,
                    destination_location_id: destinationLocationId,
                    origin_location_type: V3_LOCATION_TYPES.AIRPORT,
                    destination_location_type: V3_LOCATION_TYPES.AIRPORT,
                    cargo_type: isDangerousGoods ? V3_CARGO_TYPES.DANGEROUS_GOODS : V3_CARGO_TYPES.GENERAL,
                    dimensions: dimensions,
                };

                setInitialData(formData);

                // 2. Hydrate UI State (Customer, Contacts, Locations)

                // Customer
                if (customerId) {
                    const custRef = quote.customer as QuoteCustomerRef;
                    if (custRef && typeof custRef === 'object') {
                        setInitialCustomer({
                            id: custRef.id || customerId,
                            name: custRef.company_name || custRef.name || "Customer",
                        } as CompanySearchResult);
                    }
                    // Fetch contacts!
                    try {
                        const contacts = await getContactsForCompany(customerId);
                        setInitialContacts(contacts);
                    } catch (e) {
                        console.error("Failed to fetch contacts", e);
                    }
                }

                // Locations
                if (originLocationId) {
                    setInitialOrigin({
                        id: originLocationId,
                        display_name: quote.origin_location as string || originLocationId,
                        code: originAirportCode || "ORG",
                        type: 'AIRPORT',
                        country_code: 'PG'
                    } as LocationSearchResult);
                }

                if (destinationLocationId) {
                    setInitialDestination({
                        id: destinationLocationId,
                        display_name: quote.destination_location as string || destinationLocationId,
                        code: destinationAirportCode || "DST",
                        type: 'AIRPORT',
                        country_code: 'AU'
                    } as LocationSearchResult);
                }

            } catch (err) {
                console.error("Error loading quote:", err);
                setApiError("Failed to load quote details.");
            } finally {
                setIsLoading(false);
            }
        };

        if (user && id) {
            loadQuote();
        }
    }, [id, user]);


    const handleQuoteSubmit = async (data: QuoteFormSchemaV3) => {
        setIsSubmitting(true);
        setApiError(null);
        setMissingRates({ carrier: false, agent: false });

        try {
            // Pass the existing quote ID to update it (or create new version)
            const payload = buildQuoteComputePayload(data, undefined, id);
            const response = await computeQuoteV3(payload);

            // Check for missing rates
            const hasMissingRates = response.latest_version?.totals?.has_missing_rates ?? false;
            if (hasMissingRates) {
                const lines = response.latest_version?.lines ?? [];
                let missingCarrier = false;
                let missingAgent = false;

                // Check for missing carrier rates (FRT_AIR_EXP)
                if (lines.some(l => l.service_component?.code === 'FRT_AIR_EXP' && l.is_rate_missing)) {
                    missingCarrier = true;
                }

                // Check for missing agent rates
                const destComponents = ['DST-DELIV-STD', 'DST-CLEAR-CUS', 'DST-HANDL-STD', 'DST-DOC-IMP', 'DST_CHARGES'];
                if (lines.some(l => destComponents.includes(l.service_component?.code || '') && l.is_rate_missing)) {
                    missingAgent = true;
                }

                if (missingCarrier || missingAgent) {
                    setMissingRates({ carrier: missingCarrier, agent: missingAgent });
                    setShowMissingRatesModal(true);
                    setIsSubmitting(false);
                    return;
                }
            }

            router.push(`/quotes/${response.id}`);
        } catch (error: unknown) {
            console.error("API Error:", error);
            const message = error instanceof Error ? error.message : "An unexpected error occurred.";
            setApiError(message);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleMissingRatesDone = () => {
        setShowMissingRatesModal(false);
        if (id) {
            router.push(`/quotes/${id}`);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center p-20">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <span className="ml-2">Loading quote...</span>
            </div>
        );
    }

    if (apiError && !initialData) {
        return (
            <div className="container mx-auto p-8">
                <div className="text-red-500 font-bold mb-4">Error</div>
                <p>{apiError}</p>
            </div>
        );
    }

    return (
        <div className="container mx-auto max-w-5xl p-4 pb-32">
            <Breadcrumb className="mb-6">
                <BreadcrumbList>
                    <BreadcrumbItem>
                        <BreadcrumbLink href="/dashboard">Dashboard</BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                        <BreadcrumbLink href="/quotes">Quotes</BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                        <BreadcrumbLink href={`/quotes/${id}`}>{id.split('-')[0]}...</BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                        <BreadcrumbPage>Edit</BreadcrumbPage>
                    </BreadcrumbItem>
                </BreadcrumbList>
            </Breadcrumb>
            {initialData && (
                <QuoteForm
                    user={user}
                    defaultValues={initialData}
                    initialCustomer={initialCustomer}
                    initialContacts={initialContacts}
                    initialOrigin={initialOrigin}
                    initialDestination={initialDestination}
                    onSubmit={handleQuoteSubmit}
                    isSubmitting={isSubmitting}
                    serverError={apiError}
                    isEditMode={true}
                />
            )}

            {showMissingRatesModal && (
                <MissingRatesModal
                    isOpen={showMissingRatesModal}
                    onClose={() => setShowMissingRatesModal(false)}
                    onSubmit={handleMissingRatesDone}
                    missingRates={{ carrier: missingRates.carrier, agent: missingRates.agent }}
                    quoteId={id}
                    shipmentDetails={{
                        origin: "Quote Origin",
                        destination: "Quote Destination",
                        mode: "AIR",
                        pieces: 1,
                        weight: 1,
                        chargeableWeight: 1,
                        serviceScope: "A2A"
                    }}
                />
            )}
        </div>
    );
}
