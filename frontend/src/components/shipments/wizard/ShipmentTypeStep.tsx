"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SHIPMENT_TYPE_OPTIONS } from "@/lib/shipment-types";

import type { ShipmentTypeStepProps } from "./shipment-wizard-types";

export default function ShipmentTypeStep({ form, updateField }: ShipmentTypeStepProps) {
  const shipmentTypeOptions = form.shipment_type === "IMPORT"
    ? [
        { value: "IMPORT" as const, label: "Import (Legacy)", description: "Legacy inbound shipment preserved for editing." },
        ...SHIPMENT_TYPE_OPTIONS.map((option) => ({
          ...option,
          description: option.value === "DOMESTIC"
            ? "Operational workflow for PNG domestic movements only."
            : "Lean export workflow with optional export references and customs notes.",
        })),
      ]
    : SHIPMENT_TYPE_OPTIONS.map((option) => ({
        ...option,
        description: option.value === "DOMESTIC"
          ? "Operational workflow for PNG domestic movements only."
          : "Lean export workflow with optional export references and customs notes.",
      }));

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader><CardTitle>Shipment Type and Branch</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          {shipmentTypeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`rounded-xl border px-4 py-4 text-left transition-all duration-200 hover:-translate-y-px hover:shadow-sm active:translate-y-0 active:scale-[0.99] ${form.shipment_type === option.value ? "border-sky-500 bg-sky-50 text-sky-900" : "border-slate-200 bg-white text-slate-700 hover:border-sky-200"}`}
              onClick={() => updateField("shipment_type", option.value)}
            >
              <div className="font-semibold">{option.label}</div>
              <div className="mt-1 text-sm text-slate-500">{option.description}</div>
            </button>
          ))}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <Input placeholder="Branch" value={form.branch} onChange={(event) => updateField("branch", event.target.value.toUpperCase())} />
          <Input type="date" value={form.shipment_date} onChange={(event) => updateField("shipment_date", event.target.value)} />
        </div>
      </CardContent>
    </Card>
  );
}
