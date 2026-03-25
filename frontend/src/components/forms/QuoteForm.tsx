"use client";

import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useWatch } from "react-hook-form";
import { AlertTriangle } from "lucide-react";

import ProgressSectionCard from "@/components/forms/ProgressSectionCard";
import QuoteWorkflowActionBar from "@/components/forms/QuoteWorkflowActionBar";
import QuoteCargoSection from "@/components/forms/quote-sections/QuoteCargoSection";
import QuoteCustomerSection from "@/components/forms/quote-sections/QuoteCustomerSection";
import QuoteRouteSection from "@/components/forms/quote-sections/QuoteRouteSection";
import QuoteTermsSection from "@/components/forms/quote-sections/QuoteTermsSection";
import { SummaryCard, SummaryStack, type SummaryLine } from "@/components/ui/summary-card";
import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { useQuoteLogic } from "@/hooks/useQuoteLogic";
import {
  formatIncoterm,
  formatPaymentTerm,
  formatPieceLabel,
  formatRouteCodes,
  formatRouteName,
  formatServiceScope,
  joinDisplayValues,
} from "@/lib/display";
import { type QuoteFormSchemaV3, V3_CARGO_TYPES } from "@/lib/schemas/quoteSchema";
import type {
  CompanySearchResult,
  Contact,
  LocationSearchResult,
  User,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const getCompletedFieldClass = (isComplete: boolean) =>
  isComplete
    ? "border-primary bg-primary text-white ring-1 ring-primary/25 hover:border-primary hover:bg-primary/95 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 [&_svg]:text-white/80"
    : "";

const hasText = (value: unknown) =>
  typeof value === "string" && value.trim().length > 0;

const isPositiveValue = (value: unknown) => {
  const numericValue =
    typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  return Number.isFinite(numericValue) && numericValue > 0;
};

const compactSummaryLines = (lines: SummaryLine[]) => lines.filter((line) => Boolean(line.text));

const cloneValue = <T,>(value: T): T => {
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(value);
  }

  return JSON.parse(JSON.stringify(value)) as T;
};

type QuoteSectionStatus = "active" | "completed";
type QuoteSectionIndex = 0 | 1 | 2 | 3 | 4;

type QuoteSavedSnapshot = {
  values: QuoteFormSchemaV3;
  selectedCustomer: CompanySearchResult | null;
  selectedCustomerId: string | null;
  contacts: Contact[];
  originLocation: LocationSearchResult | null;
  destinationLocation: LocationSearchResult | null;
};

interface QuoteFormProps {
  defaultValues?: Partial<QuoteFormSchemaV3>;
  initialCustomer?: CompanySearchResult;
  initialContacts?: Contact[];
  initialOrigin?: LocationSearchResult;
  initialDestination?: LocationSearchResult;
  user?: User | null;
  onSubmit: (data: QuoteFormSchemaV3) => Promise<void>;
  isSubmitting?: boolean;
  serverError?: string | null;
  isEditMode?: boolean;
  onDirtyChange?: (isDirty: boolean) => void;
  onCancel?: () => void;
  cancelLabel?: string;
}

export function QuoteForm({
  defaultValues,
  initialCustomer,
  initialContacts,
  initialOrigin,
  initialDestination,
  user,
  onSubmit,
  isSubmitting = false,
  serverError,
  isEditMode = false,
  onDirtyChange,
  onCancel,
  cancelLabel = "Cancel quote",
}: QuoteFormProps) {
  const {
    form,
    fields,
    append,
    remove,
    cargoMetrics,
    internalError,
    contacts,
    setContacts,
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
    setInternalError,
  } = useQuoteLogic({
    defaultValues,
    initialCustomer,
    initialContacts,
    initialOrigin,
    initialDestination,
    user,
    onSubmit,
    isEditMode,
  });

  const watchedValues = useWatch({
    control: form.control,
  });

  const isImport = destinationLocation?.country_code === "PG";
  const submitBusy = isSubmitting || form.formState.isSubmitting;

  const buildSnapshot = useCallback(
    (): QuoteSavedSnapshot => ({
      values: cloneValue(form.getValues()),
      selectedCustomer: selectedCustomer ? cloneValue(selectedCustomer) : null,
      selectedCustomerId,
      contacts: cloneValue(contacts),
      originLocation: originLocation ? cloneValue(originLocation) : null,
      destinationLocation: destinationLocation ? cloneValue(destinationLocation) : null,
    }),
    [contacts, destinationLocation, form, originLocation, selectedCustomer, selectedCustomerId],
  );

  const restoreSnapshot = (snapshot: QuoteSavedSnapshot) => {
    form.reset(cloneValue(snapshot.values), { keepDefaultValues: true });
    setSelectedCustomer(snapshot.selectedCustomer ? cloneValue(snapshot.selectedCustomer) : null);
    setSelectedCustomerId(snapshot.selectedCustomerId);
    setContacts(cloneValue(snapshot.contacts));
    setOriginLocation(snapshot.originLocation ? cloneValue(snapshot.originLocation) : null);
    setDestinationLocation(snapshot.destinationLocation ? cloneValue(snapshot.destinationLocation) : null);
    setInternalError(null);
  };

  const customerComplete =
    hasText(watchedValues.customer_id) && hasText(watchedValues.contact_id);
  const routeComplete =
    hasText(watchedValues.mode) &&
    hasText(watchedValues.service_scope) &&
    hasText(watchedValues.origin_location_id) &&
    hasText(watchedValues.destination_location_id) &&
    /^[A-Z]{3}$/.test((watchedValues.origin_airport || "").trim().toUpperCase()) &&
    /^[A-Z]{3}$/.test((watchedValues.destination_airport || "").trim().toUpperCase());
  const termsComplete =
    hasText(watchedValues.payment_term) &&
    hasText(watchedValues.incoterm) &&
    validIncoterms.includes(watchedValues.incoterm || "");
  const cargoComplete =
    hasText(watchedValues.cargo_type) &&
    Array.isArray(watchedValues.dimensions) &&
    watchedValues.dimensions.length > 0 &&
    watchedValues.dimensions.every((dimension) => (
      isPositiveValue(dimension?.pieces) &&
      isPositiveValue(dimension?.length_cm) &&
      isPositiveValue(dimension?.width_cm) &&
      isPositiveValue(dimension?.height_cm) &&
      isPositiveValue(dimension?.gross_weight_kg) &&
      hasText(dimension?.package_type)
    ));

  const sequentialValidityIndex = useMemo<QuoteSectionIndex>(() => {
    if (!customerComplete) return 0;
    if (!routeComplete) return 1;
    if (!termsComplete) return 2;
    if (!cargoComplete) return 3;
    return 4;
  }, [cargoComplete, customerComplete, routeComplete, termsComplete]);

  const [savedProgressIndex, setSavedProgressIndex] = useState<QuoteSectionIndex>(sequentialValidityIndex);
  const [savedSnapshot, setSavedSnapshot] = useState<QuoteSavedSnapshot>(() => buildSnapshot());
  const [sectionSnapshots, setSectionSnapshots] = useState<Partial<Record<QuoteSectionIndex, QuoteSavedSnapshot>>>({});
  const [furthestSection, setFurthestSection] = useState<QuoteSectionIndex>(sequentialValidityIndex);
  const [activeSection, setActiveSection] = useState<QuoteSectionIndex>(sequentialValidityIndex);
  const [recentlyRevealedSection, setRecentlyRevealedSection] = useState<QuoteSectionIndex | null>(null);

  useEffect(() => {
    onDirtyChange?.(form.formState.isDirty);
  }, [form.formState.isDirty, onDirtyChange]);

  useEffect(() => {
    if (!form.formState.isDirty) {
      const nextSnapshot = buildSnapshot();
      const nextSectionSnapshots: Partial<Record<QuoteSectionIndex, QuoteSavedSnapshot>> = {};

      for (let index = 0; index < sequentialValidityIndex; index += 1) {
        nextSectionSnapshots[index as QuoteSectionIndex] = nextSnapshot;
      }

      setSavedSnapshot(nextSnapshot);
      setSectionSnapshots(nextSectionSnapshots);
      setSavedProgressIndex(sequentialValidityIndex);
      setFurthestSection(sequentialValidityIndex);
      setActiveSection(sequentialValidityIndex);
      setRecentlyRevealedSection(null);
      return;
    }

    setFurthestSection(() => {
      const nextVisibleSection = Math.min(savedProgressIndex, sequentialValidityIndex) as QuoteSectionIndex;
      return nextVisibleSection;
    });
  }, [
    buildSnapshot,
    form,
    form.formState.isDirty,
    savedProgressIndex,
    sequentialValidityIndex,
  ]);

  useEffect(() => {
    setActiveSection((current) => Math.min(current, furthestSection) as QuoteSectionIndex);
  }, [furthestSection]);

  useEffect(() => {
    if (recentlyRevealedSection === null) {
      return;
    }

    const timer = window.setTimeout(() => {
      setRecentlyRevealedSection(null);
    }, 300);

    return () => window.clearTimeout(timer);
  }, [recentlyRevealedSection]);

  const canSubmit = form.formState.isValid && cargoComplete && furthestSection >= 4 && !submitBusy;
  const isEditingCommittedSection =
    activeSection < savedProgressIndex && Boolean(sectionSnapshots[activeSection]);

  const contactName = useMemo(() => {
    const selectedContact = contacts.find((contact) => contact.id === watchedValues.contact_id);
    return selectedContact
      ? `${selectedContact.first_name} ${selectedContact.last_name}`.trim()
      : "";
  }, [contacts, watchedValues.contact_id]);

  const originCode = (watchedValues.origin_airport || originLocation?.code || "")
    .trim()
    .toUpperCase();
  const destinationCode = (watchedValues.destination_airport || destinationLocation?.code || "")
    .trim()
    .toUpperCase();
  const routeNameLabel = formatRouteName(
    originLocation,
    destinationLocation,
    originCode,
    destinationCode,
  );
  const routeCodeLabel = joinDisplayValues([
    formatRouteCodes(originCode, destinationCode),
    watchedValues.service_scope || "",
  ]);
  const serviceScopeLabel = formatServiceScope(watchedValues.service_scope, "");
  const paymentTermLabel = formatPaymentTerm(watchedValues.payment_term, "");
  const incotermLabel = formatIncoterm(watchedValues.incoterm || "", { fallback: "" });
  const marketLabel = isImport ? "Import" : "Export / Domestic";
  const shipmentTypeLabel = watchedValues.cargo_type || V3_CARGO_TYPES.GENERAL;
  const shipmentMetricsLabel = joinDisplayValues([
    formatPieceLabel(cargoMetrics.pieces),
    `${cargoMetrics.chargeableWeight} kg chargeable`,
  ]);

  const customerSummaryLines: SummaryLine[] = customerComplete
    ? [
        { text: selectedCustomer?.name || "Customer selected", emphasis: "primary" },
        ...(contactName ? [{ text: contactName, emphasis: "secondary" as const }] : []),
      ]
    : [{ text: "Select the customer and contact person to begin the quote.", emphasis: "secondary" }];
  const routeSummaryLines: SummaryLine[] = routeComplete
    ? compactSummaryLines([
        { text: routeNameLabel, emphasis: "primary" },
        { text: serviceScopeLabel, emphasis: "secondary" },
        { text: routeCodeLabel, emphasis: "tertiary" },
      ])
    : [{ text: "Choose the mode, service scope, origin, and destination.", emphasis: "secondary" }];
  const termsSummaryLines: SummaryLine[] = termsComplete
    ? compactSummaryLines([
        { text: joinDisplayValues([paymentTermLabel, incotermLabel]), emphasis: "primary" },
        { text: marketLabel, emphasis: "secondary" },
      ])
    : [{ text: "Confirm the payment term and valid incoterm.", emphasis: "secondary" }];
  const shipmentSummaryLines: SummaryLine[] = cargoComplete
    ? [
        { text: shipmentTypeLabel, emphasis: "primary" },
        { text: shipmentMetricsLabel, emphasis: "secondary" },
      ]
    : [{ text: "Add at least one complete cargo line with pieces, dimensions, and weight.", emphasis: "secondary" }];
  const reviewSummary: ReactNode = (
    <SummaryStack
      lines={[
        {
          text: furthestSection >= 4
            ? "Review your quote before sending."
            : "Finish the shipment details to unlock quote review.",
          emphasis: "secondary",
        },
      ]}
    />
  );

  const scrollToSection = (index: QuoteSectionIndex) => {
    window.requestAnimationFrame(() => {
      document
        .getElementById(`quote-section-${index}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const openSection = (index: QuoteSectionIndex) => {
    setActiveSection(index);
    scrollToSection(index);
  };

  const commitSection = (sectionIndex: QuoteSectionIndex, nextIndex: QuoteSectionIndex) => {
    const snapshot = buildSnapshot();
    const nextSavedProgress = Math.max(nextIndex, sequentialValidityIndex) as QuoteSectionIndex;
    const nextSectionSnapshots: Partial<Record<QuoteSectionIndex, QuoteSavedSnapshot>> = {};

    for (let index = 0; index < nextSavedProgress; index += 1) {
      nextSectionSnapshots[index as QuoteSectionIndex] = snapshot;
    }

    setSavedSnapshot(snapshot);
    setSectionSnapshots((current) => ({
      ...current,
      ...nextSectionSnapshots,
      [sectionIndex]: snapshot,
    }));
    setSavedProgressIndex(nextSavedProgress);
    setFurthestSection(nextSavedProgress);
    setActiveSection(nextSavedProgress);
    setRecentlyRevealedSection(nextSavedProgress === sectionIndex ? null : nextSavedProgress);
    scrollToSection(nextSavedProgress);
  };

  const discardSectionChanges = () => {
    const snapshot = sectionSnapshots[activeSection] || savedSnapshot;
    restoreSnapshot(snapshot);
    setFurthestSection(savedProgressIndex);
    setActiveSection(savedProgressIndex);
    setRecentlyRevealedSection(null);
    scrollToSection(savedProgressIndex);
  };

  const continueWithValidation = async (
    fieldsToValidate: Array<
      | "customer_id"
      | "contact_id"
      | "mode"
      | "service_scope"
      | "origin_location_id"
      | "origin_airport"
      | "destination_location_id"
      | "destination_airport"
      | "payment_term"
      | "incoterm"
      | "cargo_type"
      | "dimensions"
    >,
    nextIndex: QuoteSectionIndex,
  ) => {
    const isValid = await form.trigger(fieldsToValidate, { shouldFocus: true });
    if (!isValid) {
      return;
    }

    commitSection(activeSection, nextIndex);
  };

  const onFormError = (errors: Record<string, unknown>) => {
    if (Object.keys(errors).length > 0) {
      console.warn("Form validation errors:", errors);
      setActiveSection(sequentialValidityIndex);
      scrollToSection(sequentialValidityIndex);
    }
  };

  const getSectionStatus = (index: QuoteSectionIndex): QuoteSectionStatus => {
    if (index === activeSection) return "active";
    return "completed";
  };

  const renderGlobalCancelAction = () =>
    onCancel ? (
      <Button type="button" variant="outline" onClick={onCancel} disabled={submitBusy}>
        {cancelLabel}
      </Button>
    ) : null;

  const renderSectionDiscardAction = () => {
    if (isEditingCommittedSection) {
      return (
        <Button
          type="button"
          variant="outline"
          onClick={discardSectionChanges}
          disabled={submitBusy}
        >
          Discard changes
        </Button>
      );
    }

    return null;
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleFormSubmit, onFormError)} className="space-y-6">
        <div className={cn("space-y-6", submitBusy && "pointer-events-none opacity-70")}>
          {(internalError || serverError) && (
            <div className="flex items-center gap-2 rounded-md bg-destructive/15 px-4 py-3 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              <p className="text-sm font-medium">{internalError || serverError}</p>
            </div>
          )}

          <div id="quote-section-0">
            <ProgressSectionCard
              step={1}
              title="Customer Details"
              status={getSectionStatus(0)}
              summary={<SummaryStack lines={customerSummaryLines} />}
              actionLabel={getSectionStatus(0) === "completed" ? "Edit" : undefined}
              onAction={getSectionStatus(0) === "completed" ? () => openSection(0) : undefined}
            >
              <div className="space-y-6">
                <QuoteCustomerSection
                  form={form}
                  contacts={contacts}
                  isLoadingContacts={isLoadingContacts}
                  selectedCustomer={selectedCustomer}
                  selectedCustomerId={selectedCustomerId}
                  setSelectedCustomer={setSelectedCustomer}
                  setSelectedCustomerId={setSelectedCustomerId}
                  getCompletedFieldClass={getCompletedFieldClass}
                />

                <QuoteWorkflowActionBar
                  secondaryAction={renderSectionDiscardAction()}
                  primaryLabel="Continue to Route"
                  primaryDisabled={!customerComplete || submitBusy}
                  onPrimaryClick={() => void continueWithValidation(["customer_id", "contact_id"], 1)}
                />
              </div>
            </ProgressSectionCard>
          </div>

          {furthestSection >= 1 ? (
            <div
              id="quote-section-1"
              className={cn(
                recentlyRevealedSection === 1 && "animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
              )}
            >
              <ProgressSectionCard
                step={2}
                title="Route & Service"
                status={getSectionStatus(1)}
                summary={<SummaryStack lines={routeSummaryLines} />}
                actionLabel={getSectionStatus(1) === "completed" ? "Edit" : undefined}
                onAction={getSectionStatus(1) === "completed" ? () => openSection(1) : undefined}
              >
                <div className="space-y-6">
                  <QuoteRouteSection
                    form={form}
                    originLocation={originLocation}
                    destinationLocation={destinationLocation}
                    setOriginLocation={setOriginLocation}
                    setDestinationLocation={setDestinationLocation}
                    setLocationFields={setLocationFields}
                    getCompletedFieldClass={getCompletedFieldClass}
                  />

                  <QuoteWorkflowActionBar
                    secondaryAction={renderSectionDiscardAction()}
                    primaryLabel="Continue to Terms"
                    primaryDisabled={!routeComplete || submitBusy}
                    onPrimaryClick={() => void continueWithValidation([
                      "mode",
                      "service_scope",
                      "origin_location_id",
                      "origin_airport",
                      "destination_location_id",
                      "destination_airport",
                    ], 2)}
                  />
                </div>
              </ProgressSectionCard>
            </div>
          ) : null}

          {furthestSection >= 2 ? (
            <div
              id="quote-section-2"
              className={cn(
                recentlyRevealedSection === 2 && "animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
              )}
            >
              <ProgressSectionCard
                step={3}
                title="Shipment Terms"
                status={getSectionStatus(2)}
                summary={<SummaryStack lines={termsSummaryLines} />}
                actionLabel={getSectionStatus(2) === "completed" ? "Edit" : undefined}
                onAction={getSectionStatus(2) === "completed" ? () => openSection(2) : undefined}
              >
                <div className="space-y-6">
                  <QuoteTermsSection
                    form={form}
                    isImport={isImport}
                    validIncoterms={validIncoterms}
                  />

                  <QuoteWorkflowActionBar
                    secondaryAction={renderSectionDiscardAction()}
                    primaryLabel="Continue to Shipment"
                    primaryDisabled={!termsComplete || submitBusy}
                    onPrimaryClick={() => void continueWithValidation(["payment_term", "incoterm"], 3)}
                  />
                </div>
              </ProgressSectionCard>
            </div>
          ) : null}

          {furthestSection >= 3 ? (
            <div
              id="quote-section-3"
              className={cn(
                recentlyRevealedSection === 3 && "animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
              )}
            >
              <ProgressSectionCard
                step={4}
                title="Shipment Details"
                status={getSectionStatus(3)}
                summary={<SummaryStack lines={shipmentSummaryLines} />}
                actionLabel={getSectionStatus(3) === "completed" ? "Edit" : undefined}
                onAction={getSectionStatus(3) === "completed" ? () => openSection(3) : undefined}
              >
                <div className="space-y-6">
                  <QuoteCargoSection
                    form={form}
                    fields={fields}
                    append={append}
                    remove={remove}
                    cargoMetrics={cargoMetrics}
                  />

                  <QuoteWorkflowActionBar
                    secondaryAction={renderSectionDiscardAction()}
                    primaryLabel="Review Quote"
                    primaryDisabled={!cargoComplete || submitBusy}
                    onPrimaryClick={() => void continueWithValidation(["cargo_type", "dimensions"], 4)}
                  />
                </div>
              </ProgressSectionCard>
            </div>
          ) : null}

          {furthestSection >= 4 ? (
            <div
              id="quote-section-4"
              className={cn(
                recentlyRevealedSection === 4 && "animate-in fade-in-0 slide-in-from-bottom-2 duration-200",
              )}
            >
              <ProgressSectionCard
                step={5}
                title={isEditMode ? "Review Quote" : "Review & Generate Quote"}
                status={getSectionStatus(4)}
                summary={reviewSummary}
              >
                <div className="space-y-6">
                  <div className="grid gap-4 md:grid-cols-2">
                    <SummaryCard label="Customer" lines={customerSummaryLines} />
                    <SummaryCard label="Route" lines={routeSummaryLines} />
                    <SummaryCard label="Shipment" lines={shipmentSummaryLines} />
                    <SummaryCard label="Terms" lines={termsSummaryLines} />
                  </div>

                  <QuoteWorkflowActionBar
                    secondaryAction={renderGlobalCancelAction()}
                    primaryType="submit"
                    primaryLabel={isEditMode ? "Update Quote" : "Generate Quote"}
                    primaryDisabled={!canSubmit}
                    primaryLoading={submitBusy}
                    primaryLoadingText={isEditMode ? "Updating quote..." : "Generating quote..."}
                  />
                </div>
              </ProgressSectionCard>
            </div>
          ) : null}
        </div>
      </form>
    </Form>
  );
}

export default QuoteForm;
