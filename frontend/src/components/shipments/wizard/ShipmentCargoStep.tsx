"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  calculatePieceMetrics,
  type ShipmentFormData,
  SHIPMENT_CARGO_TYPE_OPTIONS,
} from "@/lib/shipment-types";

import type { ShipmentCargoStepProps } from "./shipment-wizard-types";

export default function ShipmentCargoStep({
  form,
  normalizedForm,
  totals,
  updateField,
  updatePiece,
  addPiece,
  removePiece,
}: ShipmentCargoStepProps) {
  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader><CardTitle>Cargo Details</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.cargo_type} onChange={(event) => updateField("cargo_type", event.target.value as ShipmentFormData["cargo_type"])}>
            {SHIPMENT_CARGO_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <Input placeholder="Cargo description" value={form.cargo_description} onChange={(event) => updateField("cargo_description", event.target.value)} />
        </div>

        {form.pieces.map((piece, index) => {
          const metrics = calculatePieceMetrics(piece);
          return (
            <div key={`piece-${index}`} className="space-y-3 rounded-xl border border-slate-200 p-4">
              <div className="grid gap-3 md:grid-cols-6">
                <Input type="number" min={1} placeholder="Quantity" value={piece.piece_count} onChange={(event) => updatePiece(index, "piece_count", Number(event.target.value))} />
                <Input placeholder="Package type" value={piece.package_type} onChange={(event) => updatePiece(index, "package_type", event.target.value)} />
                <Input placeholder="Length cm" value={piece.length_cm} onChange={(event) => updatePiece(index, "length_cm", event.target.value)} />
                <Input placeholder="Width cm" value={piece.width_cm} onChange={(event) => updatePiece(index, "width_cm", event.target.value)} />
                <Input placeholder="Height cm" value={piece.height_cm} onChange={(event) => updatePiece(index, "height_cm", event.target.value)} />
                <Input placeholder="Gross kg" value={piece.gross_weight_kg} onChange={(event) => updatePiece(index, "gross_weight_kg", event.target.value)} />
              </div>
              <Input placeholder="Piece description" value={piece.description} onChange={(event) => updatePiece(index, "description", event.target.value)} />
              <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">Volumetric: {metrics.volumetric.toFixed(2)} kg</div>
                <div className="rounded-lg bg-sky-50 px-3 py-2 text-sm">Chargeable: {metrics.chargeable.toFixed(2)} kg</div>
                {form.pieces.length > 1 ? <Button type="button" variant="ghost" onClick={() => removePiece(index)}>Remove</Button> : null}
              </div>
            </div>
          );
        })}

        <div className="flex items-center justify-between">
          <Button type="button" variant="outline" onClick={addPiece}>Add Piece Line</Button>
          <div className="rounded-lg bg-slate-50 px-4 py-3 text-sm font-medium">
            {totals.totalPieces} pcs | {totals.totalGrossWeightKg} kg gross | {totals.totalChargeableWeightKg} kg chargeable
          </div>
        </div>

        {normalizedForm.cargo_type === "DANGEROUS_GOODS" ? (
          <Textarea placeholder="Dangerous goods notes" value={form.dangerous_goods_details} onChange={(event) => updateField("dangerous_goods_details", event.target.value)} />
        ) : null}
        {normalizedForm.cargo_type === "PERISHABLE" ? (
          <Textarea placeholder="Perishable handling notes" value={form.perishable_details} onChange={(event) => updateField("perishable_details", event.target.value)} />
        ) : null}
        <Textarea placeholder="Special handling notes" value={form.handling_notes} onChange={(event) => updateField("handling_notes", event.target.value)} />
        <Textarea placeholder="Declaration notes" value={form.declaration_notes} onChange={(event) => updateField("declaration_notes", event.target.value)} />
      </CardContent>
    </Card>
  );
}
