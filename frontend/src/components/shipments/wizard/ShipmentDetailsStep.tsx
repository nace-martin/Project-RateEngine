"use client";

import LocationSearchCombobox from "@/components/LocationSearchCombobox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  type ShipmentFormData,
  SHIPMENT_PAYMENT_TYPE_OPTIONS,
  SHIPMENT_SERVICE_PRODUCT_OPTIONS,
} from "@/lib/shipment-types";

import type { ShipmentDetailsStepProps } from "./shipment-wizard-types";

export default function ShipmentDetailsStep({
  form,
  updateField,
  handleLocationSelect,
  serviceScopeOptions,
}: ShipmentDetailsStepProps) {
  const paymentOptions = form.payment_term === "THIRD_PARTY"
    ? [
        ...SHIPMENT_PAYMENT_TYPE_OPTIONS,
        { value: "THIRD_PARTY" as const, label: "Third Party (Legacy)" },
      ]
    : SHIPMENT_PAYMENT_TYPE_OPTIONS;

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader><CardTitle>Shipment Details</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <LocationSearchCombobox value={form.origin_location_id} selectedLabel={form.origin_location_display} onSelect={(location) => handleLocationSelect("origin", location)} placeholder="Search origin airport" />
          <LocationSearchCombobox value={form.destination_location_id} selectedLabel={form.destination_location_display} onSelect={(location) => handleLocationSelect("destination", location)} placeholder="Search destination airport" />
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.service_product} onChange={(event) => updateField("service_product", event.target.value as ShipmentFormData["service_product"])}>
            {SHIPMENT_SERVICE_PRODUCT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.service_scope} onChange={(event) => updateField("service_scope", event.target.value as ShipmentFormData["service_scope"])}>
            {serviceScopeOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.payment_term} onChange={(event) => updateField("payment_term", event.target.value as ShipmentFormData["payment_term"])}>
            {paymentOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <Input placeholder="Internal reference" value={form.reference_number} onChange={(event) => updateField("reference_number", event.target.value)} />
          <Input placeholder="Booking reference" value={form.booking_reference} onChange={(event) => updateField("booking_reference", event.target.value)} />
          <Input placeholder="Flight reference" value={form.flight_reference} onChange={(event) => updateField("flight_reference", event.target.value)} />
        </div>
        {form.shipment_type === "EXPORT" ? (
          <div className="grid gap-3 md:grid-cols-2">
            <Input placeholder="Export reference" value={form.export_reference} onChange={(event) => updateField("export_reference", event.target.value)} />
            <Input placeholder="Invoice reference" value={form.invoice_reference} onChange={(event) => updateField("invoice_reference", event.target.value)} />
            <Input placeholder="Permit reference" value={form.permit_reference} onChange={(event) => updateField("permit_reference", event.target.value)} />
            <Textarea placeholder="Customs notes" value={form.customs_notes} onChange={(event) => updateField("customs_notes", event.target.value)} />
          </div>
        ) : (
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
            Domestic shipments use the lean operational flow with no export-only prompts.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
