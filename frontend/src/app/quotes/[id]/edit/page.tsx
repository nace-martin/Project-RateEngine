"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "@/context/auth-context";
import { useToast } from "@/context/toast-context";
import { useRouter } from "next/navigation";
import { getQuoteV3, computeQuoteV3 } from "@/lib/api";
import { getContactsForCompany } from "@/lib/api/parties";
import { type QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import { CompanySearchResult, LocationSearchResult, Contact } from "@/lib/types";
import QuoteForm from "@/components/forms/QuoteForm";
import { MissingRatesModal } from "@/components/pricing/MissingRatesModal";
import { Loader2 } from "lucide-react";
import PageBackButton from "@/components/navigation/PageBackButton";
import { useConfirm } from "@/hooks/useConfirm";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useReturnTo } from "@/hooks/useReturnTo";
import {
    buildQuoteComputePayload,
    getQuoteMissingRateFlags,
} from "@/lib/quote-workflow";
import { hydrateQuoteEditForm } from "@/lib/quote-edit-hydration";
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
                const hydratedQuote = hydrateQuoteEditForm(quote);
                setInitialData(hydratedQuote.formData);

                // 2. Hydrate UI State (Customer, Contacts, Locations)

                // Customer
                if (hydratedQuote.customerId) {
                    if (hydratedQuote.initialCustomer) {
                        setInitialCustomer(hydratedQuote.initialCustomer);
                    }
                    // Fetch contacts!
                    try {
                        const contacts = await getContactsForCompany(hydratedQuote.customerId);
                        setInitialContacts(contacts);
                    } catch (e) {
                        console.error("Failed to fetch contacts", e);
                    }
                }

                // Locations
                if (hydratedQuote.initialOrigin) {
                    setInitialOrigin(hydratedQuote.initialOrigin);
                }

                if (hydratedQuote.initialDestination) {
                    setInitialDestination(hydratedQuote.initialDestination);
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
