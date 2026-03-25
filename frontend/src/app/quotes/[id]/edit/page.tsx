"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "@/context/auth-context";
import { useToast } from "@/context/toast-context";
import { useRouter } from "next/navigation";
import { getQuoteV3, computeQuoteV3, getContactsForCompany } from "@/lib/api";
import { type QuoteFormSchemaV3, V3_LOCATION_TYPES, V3_CARGO_TYPES, V3_PACKAGE_TYPES } from "@/lib/schemas/quoteSchema";
import { CompanySearchResult, LocationSearchResult, Contact, QuoteContactRef, QuoteCustomerRef, V3DimensionInput } from "@/lib/types";
import QuoteForm from "@/components/forms/QuoteForm";
import { MissingRatesModal } from "@/components/pricing/MissingRatesModal";
import { Loader2 } from "lucide-react";
import PageBackButton from "@/components/navigation/PageBackButton";
import { useConfirm } from "@/hooks/useConfirm";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useReturnTo } from "@/hooks/useReturnTo";
import { buildQuoteComputePayload, getQuoteMissingRateFlags } from "@/lib/quote-workflow";
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

export default function EditQuotePage({ params }: { params: Promise<{ id: string }> }) {
    const { id } = use(params);
    const { user } = useAuth();
    const router = useRouter();
    const { toast } = useToast();
    const confirm = useConfirm();

    const [isLoading, setIsLoading] = useState(true);
    const [initialData, setInitialData] = useState<Partial<QuoteFormSchemaV3> | null>(null);
    const [isFormDirty, setIsFormDirty] = useState(false);

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
    useUnsavedChangesGuard(isFormDirty);
    const returnTo = useReturnTo() || `/quotes/${id}`;
    const confirmLeave = async () => {
        if (!isFormDirty) {
            return true;
        }
        return confirm({
            title: "Discard quote changes?",
            description: "You have unsaved quote changes. Leaving now will discard them.",
            confirmLabel: "Discard changes",
            cancelLabel: "Stay here",
            variant: "destructive",
        });
    };
    const handleCancel = async () => {
        if (!await confirmLeave()) {
            return;
        }
        router.push(returnTo);
    };

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
                let dimensions: QuoteFormSchemaV3["dimensions"] = [{
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
                        package_type: Object.values(V3_PACKAGE_TYPES).includes(d.package_type as typeof V3_PACKAGE_TYPES[keyof typeof V3_PACKAGE_TYPES])
                            ? (d.package_type as typeof V3_PACKAGE_TYPES[keyof typeof V3_PACKAGE_TYPES])
                            : V3_PACKAGE_TYPES.BOX,
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
                const { carrier: missingCarrier, agent: missingAgent } = getQuoteMissingRateFlags(response);

                if (missingCarrier || missingAgent) {
                    setMissingRates({ carrier: missingCarrier, agent: missingAgent });
                    setShowMissingRatesModal(true);
                    setIsSubmitting(false);
                    return;
                }
            }

            toast({
                title: "Quote updated",
                description: "The quote was recalculated successfully.",
                variant: "success",
            });
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
            <PageBackButton
                fallbackHref={`/quotes/${id}`}
                returnTo={returnTo}
                isDirty={isFormDirty}
                confirmLeave={confirmLeave}
                disabled={isSubmitting}
                className="mb-4 -ml-2 gap-2 px-2 text-slate-600 hover:text-slate-900"
            />
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
                    onDirtyChange={setIsFormDirty}
                    onCancel={handleCancel}
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
