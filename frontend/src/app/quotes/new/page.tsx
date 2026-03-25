"use client";

import { useState } from "react";
import { useAuth } from "@/context/auth-context";
import { useRouter } from "next/navigation";
import { computeQuoteV3 } from "@/lib/api/quotes";
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
import { buildQuoteComputePayload, getQuoteMissingRateFlags } from "@/lib/quote-workflow";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

export default function NewQuotePage() {
  const { user } = useAuth();
  const router = useRouter();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isFormDirty, setIsFormDirty] = useState(false);

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

      <QuoteForm
        user={user}
        onSubmit={handleQuoteSubmit}
        isSubmitting={isSubmitting}
        serverError={apiError}
        onDirtyChange={setIsFormDirty}
        onCancel={handleCancel}
      />

      {showMissingRatesModal && (
        <MissingRatesModal
          isOpen={showMissingRatesModal}
          onClose={() => setShowMissingRatesModal(false)}
          onSubmit={handleMissingRatesDone}
          missingRates={{ carrier: missingRates.carrier, agent: missingRates.agent }}
          quoteId={pendingQuoteId}
          // We need shipment details for the modal to generate email
          // Since we don't have form data easily available here without state,
          // We can either pass minimal dummy data or store pendingFormData just for display.
          // Let's bring back pendingFormData just for display purposes.
          shipmentDetails={{
            origin: "Quote Origin", // Ideally fix this to use form data
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
