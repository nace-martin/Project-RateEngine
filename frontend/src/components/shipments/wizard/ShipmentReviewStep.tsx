"use client";

import { CheckCircle2 } from "lucide-react";

import { SummaryCard, type SummaryLine } from "@/components/ui/summary-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatPaymentTerm,
  formatPieceLabel,
  formatRouteCodes,
  formatRouteName,
  formatServiceScope,
  joinDisplayValues,
} from "@/lib/display";
import { formatShipmentChoice } from "@/lib/shipment-types";

import type { ShipmentReviewStepProps } from "./shipment-wizard-types";

export default function ShipmentReviewStep({ normalizedForm, totals }: ShipmentReviewStepProps) {
  const customerLines: SummaryLine[] = [
    { text: normalizedForm.shipper_company_name || "Shipper", emphasis: "primary" },
    { text: normalizedForm.consignee_company_name || "Consignee", emphasis: "secondary" },
  ];

  const routeLines: SummaryLine[] = [
    {
      text: formatRouteName(
        { display_name: normalizedForm.origin_location_display || normalizedForm.origin_code || "Origin" },
        { display_name: normalizedForm.destination_location_display || normalizedForm.destination_code || "Destination" },
        normalizedForm.origin_code || "",
        normalizedForm.destination_code || "",
      ),
      emphasis: "primary",
    },
    { text: formatServiceScope(normalizedForm.service_scope), emphasis: "secondary" },
    {
      text: formatRouteCodes(normalizedForm.origin_code, normalizedForm.destination_code),
      emphasis: "tertiary",
    },
  ];

  const shipmentLines: SummaryLine[] = [
    {
      text: joinDisplayValues([
        formatShipmentChoice(normalizedForm.shipment_type),
        normalizedForm.branch || "",
      ]),
      emphasis: "primary",
    },
    {
      text: joinDisplayValues([
        formatShipmentChoice(normalizedForm.service_product),
        formatShipmentChoice(normalizedForm.cargo_type),
      ]),
      emphasis: "secondary",
    },
    {
      text: joinDisplayValues([
        formatPieceLabel(totals.totalPieces),
        `${totals.totalChargeableWeightKg} kg chargeable`,
      ]),
      emphasis: "tertiary",
    },
  ];

  const termsLines: SummaryLine[] = [
    { text: formatPaymentTerm(normalizedForm.payment_term), emphasis: "primary" },
    { text: normalizedForm.shipment_date || "Shipment date pending", emphasis: "secondary" },
  ];

  return (
    <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
      <Card className="border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>Review Shipment</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div className="grid gap-3 md:grid-cols-2">
            <SummaryCard label="Customer" lines={customerLines} className="rounded-xl" />
            <SummaryCard label="Route" lines={routeLines} className="rounded-xl" />
            <SummaryCard label="Shipment" lines={shipmentLines} className="rounded-xl" />
            <SummaryCard label="Terms" lines={termsLines} className="rounded-xl" />
          </div>

          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              Cargo Notes
            </p>
            <p className="mt-2 font-semibold text-slate-900">
              {normalizedForm.cargo_description || "General cargo"}
            </p>
            <p className="mt-1 text-muted-foreground">
              {formatShipmentChoice(normalizedForm.cargo_type)}
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              References
            </p>
            <p className="mt-2 text-slate-700">
              Internal reference: {normalizedForm.reference_number || "-"}
            </p>
            <p className="text-slate-700">
              Booking reference: {normalizedForm.booking_reference || "-"}
            </p>
            <p className="text-slate-700">
              Flight reference: {normalizedForm.flight_reference || "-"}
            </p>
            {normalizedForm.shipment_type === "EXPORT" ? (
              <>
                <p className="text-slate-700">
                  Export reference: {normalizedForm.export_reference || "-"}
                </p>
                <p className="text-slate-700">
                  Invoice reference: {normalizedForm.invoice_reference || "-"}
                </p>
                <p className="text-slate-700">
                  Permit reference: {normalizedForm.permit_reference || "-"}
                </p>
              </>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-200 bg-slate-50 shadow-sm">
        <CardHeader>
          <CardTitle>Ready to Finalize</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {[
            `${formatShipmentChoice(normalizedForm.shipment_type)} shipment ready`,
            `${normalizedForm.branch || "Branch pending"} branch recorded`,
            "Shipper and consignee details completed",
            "Origin and destination selected",
            `${formatPieceLabel(totals.totalPieces)} prepared`,
            `${totals.totalChargeableWeightKg} kg chargeable weight calculated`,
            "Connote will be generated without pricing shown",
          ].map((item) => (
            <div key={item} className="flex items-center gap-3 rounded-xl bg-white px-4 py-3 shadow-sm">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <span>{item}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
