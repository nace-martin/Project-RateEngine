"use client";

import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/context/auth-context";
import { useRouter, useSearchParams } from "next/navigation";
import { computeQuoteV3 } from "@/lib/api/quotes";
import { getCompany, getLocation, searchLocations } from "@/lib/api/parties";
import { useToast } from "@/context/toast-context";
import { type QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import QuoteForm from "@/components/forms/QuoteForm";
import { MissingRatesModal } from "@/components/pricing/MissingRatesModal";
import WorkspaceContextCard from "@/components/WorkspaceContextCard";
import PageBackButton from "@/components/navigation/PageBackButton";
import { useConfirm } from "@/hooks/useConfirm";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useReturnTo } from "@/hooks/useReturnTo";
import { getNewQuoteCopy } from "@/lib/page-copy";
import { buildQuotePrefillDefaults } from "@/lib/crm-quote-prefill";
import { buildQuoteComputePayload, getQuoteMissingRateFlags } from "@/lib/quote-workflow";
import type { CompanySearchResult, LocationSearchResult } from "@/lib/types";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const resolveLocationParam = async (value: string | null): Promise<LocationSearchResult | undefined> => {
  const normalized = (value || "").trim();
  if (!normalized) return undefined;

  if (UUID_PATTERN.test(normalized)) {
    return getLocation(normalized);
  }

  const matches = await searchLocations(normalized);
  const upper = normalized.toUpperCase();
  return matches.find((location) => location.code.toUpperCase() === upper) || matches[0];
};

function NewQuoteContent() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isFormDirty, setIsFormDirty] = useState(false);

  // Initial data from query params
  const [initialCustomer, setInitialCustomer] = useState<CompanySearchResult | undefined>(undefined);
  const [initialOrigin, setInitialOrigin] = useState<LocationSearchResult | undefined>(undefined);
  const [initialDestination, setInitialDestination] = useState<LocationSearchResult | undefined>(undefined);
  const [defaultValues, setDefaultValues] = useState<Partial<QuoteFormSchemaV3> | undefined>(undefined);
  const [unsupportedServiceType, setUnsupportedServiceType] = useState<string | undefined>(undefined);
  const [isLoadingInitial, setIsLoadingInitial] = useState(false);

  useEffect(() => {
    const customerId = searchParams.get("company");
    const opportunityId = searchParams.get("opportunity");
    const serviceType = searchParams.get("service_type");
    const originParam = searchParams.get("origin");
    const destinationParam = searchParams.get("destination");

    if (customerId || originParam || destinationParam || serviceType || opportunityId) {
      const fetchInitial = async () => {
        setIsLoadingInitial(true);
        try {
          const [customer, origin, destination] = await Promise.all([
            customerId ? getCompany(customerId) : Promise.resolve(undefined),
            resolveLocationParam(originParam),
            resolveLocationParam(destinationParam),
          ]);

          if (customer) setInitialCustomer(customer);
          if (origin) setInitialOrigin(origin);
          if (destination) setInitialDestination(destination);

          const prefill = buildQuotePrefillDefaults({
            companyId: customerId,
            opportunityId,
            serviceType,
            originLocationId: origin?.id,
            destinationLocationId: destination?.id,
            originCode: origin?.code,
            destinationCode: destination?.code,
          });
          setDefaultValues(prefill.defaultValues);
          setUnsupportedServiceType(prefill.unsupportedServiceType);
        } catch (err) {
          console.error("Failed to load initial data from params", err);
        } finally {
          setIsLoadingInitial(false);
        }
      };
      void fetchInitial();
    }
  }, [searchParams]);

  // Missing Rates State
  const [missingRates, setMissingRates] = useState({ carrier: false, agent: false });
  const [showMissingRatesModal, setShowMissingRatesModal] = useState(false);
  const [pendingQuoteId, setPendingQuoteId] = useState<string | null>(null);
  useUnsavedChangesGuard(isFormDirty);
  const returnTo = useReturnTo();
  const pageCopy = getNewQuoteCopy(user?.role as "admin" | "manager" | "sales" | "finance" | undefined);

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
    router.push(returnTo || "/quotes");
  };

  const handleQuoteSubmit = async (data: QuoteFormSchemaV3) => {
    setIsSubmitting(true);
    setApiError(null);
    setMissingRates({ carrier: false, agent: false });

    try {
      // Build payload (passing pendingQuoteId if we are retrying/updating)
      const payload = buildQuoteComputePayload(data, undefined, pendingQuoteId);
      const response = await computeQuoteV3(payload);

      // Check for missing rates
      const hasMissingRates = response.latest_version?.totals?.has_missing_rates ?? false;
      if (hasMissingRates) {
        const { carrier: missingCarrier, agent: missingAgent } = getQuoteMissingRateFlags(response);

        if (missingCarrier || missingAgent) {
          setMissingRates({ carrier: missingCarrier, agent: missingAgent });
          setPendingQuoteId(response.id);
          setShowMissingRatesModal(true);
          setIsSubmitting(false);
          return;
        }
      }

      toast({
        title: "Quote Calculated",
        description: "Quote successfully created.",
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
    // User has acknowledged/copied email template
    setShowMissingRatesModal(false);
    // Determine existing shipment details for redirect if needed?
    // Actually, since quote is saved, we just go to the quote
    if (pendingQuoteId) {
      router.push(`/quotes/${pendingQuoteId}`);
    }
  };

  return (
    <div className="container mx-auto max-w-5xl p-4 pb-32">
      <PageBackButton
        fallbackHref="/quotes"
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
            <BreadcrumbPage>New Quote</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <WorkspaceContextCard
        title={pageCopy.title}
        description={pageCopy.description}
        note={pageCopy.note}
      />

      {isLoadingInitial ? (
        <div className="flex h-64 items-center justify-center rounded-lg border border-dashed">
          <p className="text-muted-foreground">Loading initial data...</p>
        </div>
      ) : (
        <>
          {unsupportedServiceType && (
            <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              This CRM opportunity uses {unsupportedServiceType}. The quote form currently supports AIR quotes only, so
              the quote mode was not prefilled from the opportunity.
            </div>
          )}
          <QuoteForm
            user={user}
            defaultValues={defaultValues}
            initialCustomer={initialCustomer}
            initialOrigin={initialOrigin}
            initialDestination={initialDestination}
            onSubmit={handleQuoteSubmit}
            isSubmitting={isSubmitting}
            serverError={apiError}
            onDirtyChange={setIsFormDirty}
            onCancel={handleCancel}
          />
        </>
      )}

      {showMissingRatesModal && (
        <MissingRatesModal
          isOpen={showMissingRatesModal}
          onClose={() => setShowMissingRatesModal(false)}
          onSubmit={handleMissingRatesDone}
          missingRates={{ carrier: missingRates.carrier, agent: missingRates.agent }}
          quoteId={pendingQuoteId}
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

export default function NewQuotePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center">Loading page...</div>}>
      <NewQuoteContent />
    </Suspense>
  );
}
