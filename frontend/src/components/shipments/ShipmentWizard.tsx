"use client";

import { ChevronLeft, ChevronRight, Save } from "lucide-react";

import PageActionBar from "@/components/navigation/PageActionBar";
import PageBackButton from "@/components/navigation/PageBackButton";
import PageCancelButton from "@/components/navigation/PageCancelButton";
import ShipmentCargoStep from "@/components/shipments/wizard/ShipmentCargoStep";
import ShipmentDetailsStep from "@/components/shipments/wizard/ShipmentDetailsStep";
import ShipmentPartiesStep from "@/components/shipments/wizard/ShipmentPartiesStep";
import ShipmentReviewStep from "@/components/shipments/wizard/ShipmentReviewStep";
import ShipmentTypeStep from "@/components/shipments/wizard/ShipmentTypeStep";
import { useShipmentWizard } from "@/components/shipments/wizard/useShipmentWizard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SERVICE_SCOPE_OPTIONS } from "@/lib/display";
import type {
  ShipmentAddressBookEntry,
  ShipmentRecord,
  ShipmentTemplate,
} from "@/lib/shipment-types";

const STEPS = [
  "Shipment Type",
  "Parties",
  "Shipment Details",
  "Cargo Details",
  "Review & Finalize",
] as const;

type Props = {
  shipmentId?: string;
  initialShipment?: ShipmentRecord | null;
  templates: ShipmentTemplate[];
  addressBookEntries: ShipmentAddressBookEntry[];
};

export default function ShipmentWizard({ shipmentId, initialShipment, templates, addressBookEntries }: Props) {
  const wizard = useShipmentWizard({
    shipmentId,
    initialShipment,
    templates,
    addressBookEntries,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <PageBackButton
          fallbackHref="/shipments"
          returnTo={wizard.returnTo}
          isDirty={wizard.isDirty}
          confirmLeave={wizard.confirmLeave}
          disabled={wizard.isSubmitting}
          className="-ml-2 gap-2 px-2 text-slate-600 hover:text-slate-900"
        />
        <PageCancelButton
          href={wizard.returnTo || "/shipments"}
          isDirty={wizard.isDirty}
          confirmLeave={wizard.confirmLeave}
          confirmMessage="Discard the current shipment changes?"
          label="Cancel Shipment"
          disabled={wizard.isSubmitting}
        />
      </div>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>{shipmentId ? "Edit Shipment Draft" : "New Shipment Wizard"}</CardTitle>
        </CardHeader>
        <CardContent className={`space-y-4 ${wizard.isSubmitting ? "pointer-events-none opacity-70" : ""}`}>
          <div className="grid gap-3 md:grid-cols-[1.6fr_1fr]">
            <div className="grid gap-3 md:grid-cols-5">
              {STEPS.map((label, index) => (
                <button
                  key={label}
                  type="button"
                  className={`rounded-xl border px-4 py-3 text-sm font-semibold transition-all duration-200 hover:-translate-y-px hover:shadow-sm active:translate-y-0 active:scale-[0.99] ${index === wizard.step ? "border-sky-500 bg-sky-50 text-sky-900" : "border-slate-200 bg-white text-slate-600 hover:border-sky-200 hover:text-slate-900"}`}
                  onClick={() => wizard.setStep(index)}
                  disabled={wizard.isSubmitting}
                >
                  {index + 1}. {label}
                </button>
              ))}
            </div>
            <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={wizard.selectedTemplateId} onChange={(event) => wizard.applyTemplate(event.target.value)} disabled={wizard.isSubmitting}>
              <option value="">Apply shipment template</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </select>
          </div>
          {wizard.stepErrors.length > 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {wizard.stepErrors.map((error) => <div key={error}>- {error}</div>)}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className={wizard.isSubmitting ? "space-y-6 pointer-events-none opacity-70" : "space-y-6"}>
        {wizard.step === 0 ? (
          <ShipmentTypeStep form={wizard.form} updateField={wizard.updateField} />
        ) : null}

        {wizard.step === 1 ? (
          <ShipmentPartiesStep
            form={wizard.form}
            updateField={wizard.updateField}
            addressBookEntries={addressBookEntries}
            applyAddressBookEntry={wizard.applyAddressBookEntry}
          />
        ) : null}

        {wizard.step === 2 ? (
          <ShipmentDetailsStep
            form={wizard.form}
            updateField={wizard.updateField}
            handleLocationSelect={wizard.handleLocationSelect}
            serviceScopeOptions={SERVICE_SCOPE_OPTIONS}
          />
        ) : null}

        {wizard.step === 3 ? (
          <ShipmentCargoStep
            form={wizard.form}
            normalizedForm={wizard.normalizedForm}
            totals={wizard.totals}
            updateField={wizard.updateField}
            updatePiece={wizard.updatePiece}
            addPiece={wizard.addPiece}
            removePiece={wizard.removePiece}
          />
        ) : null}

        {wizard.step === 4 ? (
          <ShipmentReviewStep
            normalizedForm={wizard.normalizedForm}
            totals={wizard.totals}
          />
        ) : null}
      </div>

      <PageActionBar>
        <Button type="button" variant="outline" onClick={() => wizard.setStep((current) => Math.max(0, current - 1))} disabled={wizard.step === 0 || wizard.isSubmitting}>
          <ChevronLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        {wizard.step < STEPS.length - 1 ? (
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => void wizard.persistShipment({ finalize: false, validateBeforeSave: false })}
              disabled={wizard.isSubmitting}
              loading={wizard.isSubmitting && wizard.activeAction === "draft"}
              loadingText="Saving draft..."
            >
              <Save className="mr-2 h-4 w-4" />
              Save Draft
            </Button>
            <Button type="button" onClick={wizard.goNext} disabled={!wizard.canContinue || wizard.isSubmitting}>
              Continue
              <ChevronRight className="ml-2 h-4 w-4" />
            </Button>
          </>
        ) : (
          <>
            <PageCancelButton
              href={wizard.returnTo || "/shipments"}
              isDirty={wizard.isDirty}
              confirmLeave={wizard.confirmLeave}
              confirmMessage="Discard the current shipment changes?"
              label="Cancel Shipment"
              disabled={wizard.isSubmitting}
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => void wizard.persistShipment({ finalize: false, validateBeforeSave: false })}
              disabled={wizard.isSubmitting}
              loading={wizard.isSubmitting && wizard.activeAction === "draft"}
              loadingText="Saving draft..."
            >
              Save Draft
            </Button>
            <Button
              type="button"
              onClick={() => void wizard.persistShipment({ finalize: true, validateBeforeSave: true })}
              disabled={!wizard.canFinalize || wizard.isSubmitting}
              loading={wizard.isSubmitting && wizard.activeAction === "finalize"}
              loadingText="Generating PDF..."
            >
              Finalize and Generate PDF
            </Button>
          </>
        )}
      </PageActionBar>
    </div>
  );
}
