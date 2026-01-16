"use client";

import { useState } from "react";
import { useAuth } from "@/context/auth-context";
import { useRouter } from "next/navigation";
import { computeQuoteV3 } from "@/lib/api";
import { useToast } from "@/context/toast-context";
import { type QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import { V3QuoteComputeRequest } from "@/lib/types";
import QuoteForm from "@/components/forms/QuoteForm";
import { MissingRatesModal } from "@/components/pricing/MissingRatesModal";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

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

export default function NewQuotePage() {
  const { user } = useAuth();
  const router = useRouter();
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);

  // Missing Rates State
  const [missingRates, setMissingRates] = useState({ carrier: false, agent: false });
  const [showMissingRatesModal, setShowMissingRatesModal] = useState(false);
  const [pendingQuoteId, setPendingQuoteId] = useState<string | null>(null);
  // We don't need pendingFormData anymore as the quote is already saved

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

      <QuoteForm
        onSubmit={handleQuoteSubmit}
        isSubmitting={isSubmitting}
        serverError={apiError}
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
