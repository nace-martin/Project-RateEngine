'use client';

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ChevronLeft, ChevronRight, Save } from "lucide-react";

import LocationSearchCombobox from "@/components/LocationSearchCombobox";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/context/toast-context";
import { createShipment, finalizeShipment, openShipmentPdf, updateShipment } from "@/lib/api/shipments";
import {
  buildFixedProductCharge,
  calculatePieceMetrics,
  calculateShipmentTotals,
  createDefaultChargeLine,
  createEmptyShipmentForm,
  FIXED_PRODUCT_RULES,
  formatShipmentChoice,
  isDomesticDoorToDoorRoute,
  isDomesticShipmentRoute,
  isFixedPriceProduct,
  isFixedProductRouteValid,
  normalizeShipmentForm,
  SHIPMENT_CARGO_TYPE_OPTIONS,
  SHIPMENT_SERVICE_PRODUCT_OPTIONS,
  ShipmentAddressBookEntry,
  ShipmentFormData,
  ShipmentRecord,
  ShipmentTemplate,
  shipmentToFormData,
  toShipmentPayload,
} from "@/lib/shipment-types";
import { LocationSearchResult } from "@/lib/types";

const STEPS = ["Parties", "Routing", "Cargo", "Charges", "Review"] as const;

type Props = {
  shipmentId?: string;
  initialShipment?: ShipmentRecord | null;
  templates: ShipmentTemplate[];
  addressBookEntries: ShipmentAddressBookEntry[];
};

export default function ShipmentWizard({ shipmentId, initialShipment, templates, addressBookEntries }: Props) {
  const router = useRouter();
  const { toast } = useToast();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<ShipmentFormData>(createEmptyShipmentForm());
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [stepErrors, setStepErrors] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (initialShipment) {
      setForm(shipmentToFormData(initialShipment));
    }
  }, [initialShipment]);

  const normalizedForm = useMemo(() => normalizeShipmentForm(form), [form]);
  const totals = useMemo(() => calculateShipmentTotals(normalizedForm), [normalizedForm]);
  const fixedProductRule = FIXED_PRODUCT_RULES[normalizedForm.service_product];
  const fixedCharge = useMemo(
    () => buildFixedProductCharge(normalizedForm.service_product, normalizedForm.currency),
    [normalizedForm.currency, normalizedForm.service_product],
  );
  const isForcedDoorToDoorRoute = isFixedPriceProduct(normalizedForm.service_product)
    || isDomesticDoorToDoorRoute(normalizedForm.origin_code, normalizedForm.destination_code);
  const isDomesticSelectableScopeRoute = !isForcedDoorToDoorRoute
    && isDomesticShipmentRoute(normalizedForm.origin_country_code, normalizedForm.destination_country_code);

  const updateField = <K extends keyof ShipmentFormData>(field: K, value: ShipmentFormData[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const applyTemplate = (templateId: string) => {
    setSelectedTemplateId(templateId);
    const template = templates.find((item) => item.id === templateId);
    if (!template) {
      return;
    }

    setForm((current) => ({
      ...current,
      ...template.shipment_defaults,
      ...template.shipper_defaults,
      ...template.consignee_defaults,
      pieces: template.pieces_defaults?.length ? template.pieces_defaults : current.pieces,
      charges: template.charges_defaults?.length ? template.charges_defaults : current.charges,
    }));
  };

  const applyAddressBookEntry = (entryId: string, role: "shipper" | "consignee") => {
    const entry = addressBookEntries.find((item) => item.id === entryId);
    if (!entry) {
      return;
    }

    setForm((current) => ({
      ...current,
      [`${role}_company_name`]: entry.company_name,
      [`${role}_contact_name`]: entry.contact_name,
      [`${role}_email`]: entry.email,
      [`${role}_phone`]: entry.phone,
      [`${role}_address_line_1`]: entry.address_line_1,
      [`${role}_address_line_2`]: entry.address_line_2,
      [`${role}_city`]: entry.city,
      [`${role}_state`]: entry.state,
      [`${role}_postal_code`]: entry.postal_code,
      [`${role}_country_code`]: entry.country_code,
    } as ShipmentFormData));
  };

  const handleLocationSelect = (field: "origin" | "destination", location: LocationSearchResult | null) => {
    if (field === "origin") {
      updateField("origin_location_id", location?.id || null);
      updateField("origin_code", location?.code || "");
      updateField("origin_country_code", location?.country_code || "");
      updateField("origin_location_display", location ? `${location.display_name} (${location.code})` : "");
      return;
    }

    updateField("destination_location_id", location?.id || null);
    updateField("destination_code", location?.code || "");
    updateField("destination_country_code", location?.country_code || "");
    updateField("destination_location_display", location ? `${location.display_name} (${location.code})` : "");
  };

  const updatePiece = (index: number, field: keyof ShipmentFormData["pieces"][number], value: string | number) => {
    setForm((current) => ({
      ...current,
      pieces: current.pieces.map((piece, pieceIndex) => pieceIndex === index ? { ...piece, [field]: value } : piece),
    }));
  };

  const updateCharge = (index: number, field: keyof ShipmentFormData["charges"][number], value: string) => {
    setForm((current) => ({
      ...current,
      charges: current.charges.map((charge, chargeIndex) => chargeIndex === index ? { ...charge, [field]: value } : charge),
    }));
  };

  const addPiece = () => {
    setForm((current) => ({
      ...current,
      pieces: [
        ...current.pieces,
        { piece_count: 1, package_type: "CTN", description: "", length_cm: "", width_cm: "", height_cm: "", gross_weight_kg: "" },
      ],
    }));
  };

  const removePiece = (index: number) => {
    setForm((current) => ({
      ...current,
      pieces: current.pieces.filter((_, pieceIndex) => pieceIndex !== index),
    }));
  };

  const addCharge = () => {
    setForm((current) => ({
      ...current,
      charges: [...current.charges, createDefaultChargeLine(current.currency)],
    }));
  };

  const removeCharge = (index: number) => {
    setForm((current) => ({
      ...current,
      charges: current.charges.filter((_, chargeIndex) => chargeIndex !== index),
    }));
  };

  const validateStep = (index: number) => {
    const errors: string[] = [];

    if (index === 0) {
      if (!normalizedForm.shipper_company_name || !normalizedForm.shipper_address_line_1 || !normalizedForm.shipper_city || !normalizedForm.shipper_country_code) {
        errors.push("Complete mandatory shipper details.");
      }
      if (!normalizedForm.consignee_company_name || !normalizedForm.consignee_address_line_1 || !normalizedForm.consignee_city || !normalizedForm.consignee_country_code) {
        errors.push("Complete mandatory consignee details.");
      }
    }

    if (index === 1) {
      if (!normalizedForm.origin_location_id || !normalizedForm.destination_location_id) {
        errors.push("Origin and destination are required.");
      }
      if (!normalizedForm.shipment_date) {
        errors.push("Shipment date is required.");
      }
      if (!normalizedForm.cargo_description.trim()) {
        errors.push("Cargo description is required.");
      }
      if (
        isFixedPriceProduct(normalizedForm.service_product)
        && !isFixedProductRouteValid(normalizedForm.origin_code, normalizedForm.destination_code, normalizedForm.service_product)
      ) {
        errors.push("Documents and Small Parcels are available only on POM-LAE routes.");
      }
    }

    if (index === 2) {
      if (!normalizedForm.pieces.length) {
        errors.push("Add at least one piece line.");
      }
      normalizedForm.pieces.forEach((piece, pieceIndex) => {
        const metrics = calculatePieceMetrics(piece);
        if (piece.piece_count <= 0 || metrics.gross <= 0 || metrics.chargeable <= 0) {
          errors.push(`Piece line ${pieceIndex + 1} must have positive dimensions and weight.`);
        }
      });
      if (normalizedForm.service_product === "SMALL_PARCELS" && Number(totals.totalGrossWeightKg) > 5) {
        errors.push("Small Parcels shipments must not exceed 5 kg total gross weight.");
      }
    }

    if (index === 3) {
      if (normalizedForm.cargo_type === "DANGEROUS_GOODS" && !normalizedForm.dangerous_goods_details.trim()) {
        errors.push("Dangerous goods details are required.");
      }
      if (normalizedForm.cargo_type === "PERISHABLE" && !normalizedForm.perishable_details.trim()) {
        errors.push("Perishable details are required.");
      }
      if (!isFixedPriceProduct(normalizedForm.service_product)) {
        normalizedForm.charges.forEach((charge, chargeIndex) => {
          if (!charge.description.trim() || Number(charge.amount) <= 0) {
            errors.push(`Charge line ${chargeIndex + 1} needs a description and positive amount.`);
          }
        });
      }
    }

    return errors;
  };

  const goNext = () => {
    const errors = validateStep(step);
    setStepErrors(errors);
    if (errors.length) {
      return;
    }
    setStep((current) => Math.min(current + 1, STEPS.length - 1));
  };

  const persistShipment = async (finalize: boolean) => {
    const validationErrors = validateStep(finalize ? 3 : step);
    setStepErrors(validationErrors);
    if (validationErrors.length) {
      if (step < 3) {
        setStep(3);
      }
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = toShipmentPayload(normalizedForm);
      const saved = shipmentId ? await updateShipment(shipmentId, payload) : await createShipment(payload);
      if (finalize) {
        const finalized = await finalizeShipment(saved.id, payload);
        await openShipmentPdf(finalized.id);
        toast({ title: "Shipment finalized", description: `Connote ${finalized.connote_number} generated.`, variant: "success" });
        router.push(`/shipments/${finalized.id}`);
      } else {
        toast({ title: "Draft saved", description: "Shipment draft saved successfully.", variant: "success" });
        router.push(`/shipments/${saved.id}`);
      }
    } catch (error: unknown) {
      toast({
        title: "Unable to save shipment",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>{shipmentId ? "Edit Shipment Draft" : "New Shipment Wizard"}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[1.6fr_1fr]">
            <div className="grid gap-3 md:grid-cols-5">
              {STEPS.map((label, index) => (
                <button
                  key={label}
                  type="button"
                  className={`rounded-xl border px-4 py-3 text-sm font-semibold ${index === step ? "border-sky-500 bg-sky-50 text-sky-900" : "border-slate-200 bg-white text-slate-600"}`}
                  onClick={() => setStep(index)}
                >
                  {index + 1}. {label}
                </button>
              ))}
            </div>
            <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={selectedTemplateId} onChange={(event) => applyTemplate(event.target.value)}>
              <option value="">Apply shipment template</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </select>
          </div>
          {stepErrors.length > 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {stepErrors.map((error) => <div key={error}>- {error}</div>)}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {step === 0 ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {(["shipper", "consignee"] as const).map((role) => (
            <Card key={role} className="border-slate-200 shadow-sm">
              <CardHeader><CardTitle className="capitalize">{role}</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <select className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm" value="" onChange={(event) => applyAddressBookEntry(event.target.value, role)}>
                  <option value="">Load from address book</option>
                  {addressBookEntries
                    .filter((entry) => entry.party_role === "BOTH" || entry.party_role === role.toUpperCase())
                    .map((entry) => (
                      <option key={entry.id} value={entry.id}>{entry.label} | {entry.company_name}</option>
                    ))}
                </select>
                <div className="grid gap-3 md:grid-cols-2">
                  <Input placeholder="Company name" value={form[`${role}_company_name`]} onChange={(event) => updateField(`${role}_company_name`, event.target.value)} />
                  <Input placeholder="Contact name" value={form[`${role}_contact_name`]} onChange={(event) => updateField(`${role}_contact_name`, event.target.value)} />
                  <Input placeholder="Email" value={form[`${role}_email`]} onChange={(event) => updateField(`${role}_email`, event.target.value)} />
                  <Input placeholder="Phone" value={form[`${role}_phone`]} onChange={(event) => updateField(`${role}_phone`, event.target.value)} />
                </div>
                <Input placeholder="Address line 1" value={form[`${role}_address_line_1`]} onChange={(event) => updateField(`${role}_address_line_1`, event.target.value)} />
                <Input placeholder="Address line 2" value={form[`${role}_address_line_2`]} onChange={(event) => updateField(`${role}_address_line_2`, event.target.value)} />
                <div className="grid gap-3 md:grid-cols-4">
                  <Input placeholder="City" value={form[`${role}_city`]} onChange={(event) => updateField(`${role}_city`, event.target.value)} />
                  <Input placeholder="State" value={form[`${role}_state`]} onChange={(event) => updateField(`${role}_state`, event.target.value)} />
                  <Input placeholder="Postcode" value={form[`${role}_postal_code`]} onChange={(event) => updateField(`${role}_postal_code`, event.target.value)} />
                  <Input placeholder="Country" value={form[`${role}_country_code`]} onChange={(event) => updateField(`${role}_country_code`, event.target.value.toUpperCase())} />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}

      {step === 1 ? (
        <Card className="border-slate-200 shadow-sm">
          <CardHeader><CardTitle>Routing, Cargo, and Product</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <LocationSearchCombobox value={form.origin_location_id} selectedLabel={form.origin_location_display} onSelect={(location) => handleLocationSelect("origin", location)} placeholder="Search origin airport" />
              <LocationSearchCombobox value={form.destination_location_id} selectedLabel={form.destination_location_display} onSelect={(location) => handleLocationSelect("destination", location)} placeholder="Search destination airport" />
            </div>
            <div className="grid gap-3 md:grid-cols-4">
              <Input type="date" value={form.shipment_date} onChange={(event) => updateField("shipment_date", event.target.value)} />
              <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.cargo_type} onChange={(event) => updateField("cargo_type", event.target.value as ShipmentFormData["cargo_type"])}>
                {SHIPMENT_CARGO_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.service_product} onChange={(event) => updateField("service_product", event.target.value as ShipmentFormData["service_product"])}>
                {SHIPMENT_SERVICE_PRODUCT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={form.payment_term} onChange={(event) => updateField("payment_term", event.target.value as ShipmentFormData["payment_term"])}>
                <option value="PREPAID">Prepaid</option>
                <option value="COLLECT">Collect</option>
                <option value="THIRD_PARTY">Third Party</option>
              </select>
            </div>
            <div className="grid gap-3 md:grid-cols-[1.3fr_1fr]">
              <Input placeholder="Internal reference" value={form.reference_number} onChange={(event) => updateField("reference_number", event.target.value)} />
              {isDomesticSelectableScopeRoute ? (
                <select
                  className="h-10 rounded-lg border border-input bg-background px-3 text-sm"
                  value={normalizedForm.service_scope}
                  onChange={(event) => updateField("service_scope", event.target.value as ShipmentFormData["service_scope"])}
                >
                  <option value="A2D">Airport to Door</option>
                  <option value="D2A">Door to Airport</option>
                </select>
              ) : (
                <Input readOnly value={formatShipmentChoice(normalizedForm.service_scope)} />
              )}
            </div>
            <Input placeholder="Cargo description" value={form.cargo_description} onChange={(event) => updateField("cargo_description", event.target.value)} />
            {fixedProductRule ? (
              <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
                <div className="font-medium">{fixedProductRule.label} auto-applies at PGK {fixedProductRule.amount} excl. GST.</div>
                <div className="mt-1">This product is restricted to POM-LAE and LAE-POM and forces the shipment scope to Door-to-Door.</div>
                {fixedProductRule.maxGrossWeightKg ? (
                  <div className="mt-1">Weight rule: total gross weight must stay at or below {fixedProductRule.maxGrossWeightKg} kg.</div>
                ) : null}
              </div>
            ) : isDomesticSelectableScopeRoute ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                Other domestic PNG routes can be set as Airport-to-Door or Door-to-Airport.
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card className="border-slate-200 shadow-sm">
          <CardHeader><CardTitle>Pieces and Weights</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {normalizedForm.service_product === "SMALL_PARCELS" ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                Small Parcels is validated against a 5 kg total gross weight limit.
              </div>
            ) : null}
            {form.pieces.map((piece, index) => {
              const metrics = calculatePieceMetrics(piece);
              return (
                <div key={`piece-${index}`} className="space-y-3 rounded-xl border border-slate-200 p-4">
                  <div className="grid gap-3 md:grid-cols-6">
                    <Input type="number" min={1} placeholder="Pieces" value={piece.piece_count} onChange={(event) => updatePiece(index, "piece_count", Number(event.target.value))} />
                    <Input placeholder="Pkg type" value={piece.package_type} onChange={(event) => updatePiece(index, "package_type", event.target.value)} />
                    <Input placeholder="Length cm" value={piece.length_cm} onChange={(event) => updatePiece(index, "length_cm", event.target.value)} />
                    <Input placeholder="Width cm" value={piece.width_cm} onChange={(event) => updatePiece(index, "width_cm", event.target.value)} />
                    <Input placeholder="Height cm" value={piece.height_cm} onChange={(event) => updatePiece(index, "height_cm", event.target.value)} />
                    <Input placeholder="Gross kg" value={piece.gross_weight_kg} onChange={(event) => updatePiece(index, "gross_weight_kg", event.target.value)} />
                  </div>
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
          </CardContent>
        </Card>
      ) : null}

      {step === 3 ? (
        <Card className="border-slate-200 shadow-sm">
          <CardHeader><CardTitle>Charges and Notes</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {isFixedPriceProduct(normalizedForm.service_product) ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
                <div className="font-medium">Fixed domestic pricing is active.</div>
                {fixedCharge ? (
                  <div className="mt-2">{fixedCharge.description}: {normalizedForm.currency} {fixedCharge.amount}</div>
                ) : null}
                <div className="mt-1">Manual charge editing is disabled for this product.</div>
              </div>
            ) : (
              <>
                {form.charges.map((charge, index) => (
                  <div key={`charge-${index}`} className="grid gap-3 rounded-xl border border-slate-200 p-4 md:grid-cols-[1fr_1.3fr_0.8fr_0.8fr_0.9fr_auto]">
                    <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={charge.charge_type} onChange={(event) => updateCharge(index, "charge_type", event.target.value)}>
                      <option value="FREIGHT">Freight</option>
                      <option value="HANDLING">Handling</option>
                      <option value="SECURITY">Security</option>
                      <option value="DOCUMENTATION">Documentation</option>
                      <option value="FUEL">Fuel</option>
                      <option value="OTHER">Other</option>
                    </select>
                    <Input placeholder="Description" value={charge.description} onChange={(event) => updateCharge(index, "description", event.target.value)} />
                    <Input placeholder="Amount" value={charge.amount} onChange={(event) => updateCharge(index, "amount", event.target.value)} />
                    <Input placeholder="Currency" value={charge.currency} onChange={(event) => updateCharge(index, "currency", event.target.value.toUpperCase())} />
                    <select className="h-10 rounded-lg border border-input bg-background px-3 text-sm" value={charge.payment_by} onChange={(event) => updateCharge(index, "payment_by", event.target.value)}>
                      <option value="SHIPPER">Shipper</option>
                      <option value="CONSIGNEE">Consignee</option>
                      <option value="THIRD_PARTY">Third Party</option>
                    </select>
                    {form.charges.length > 1 ? <Button type="button" variant="ghost" onClick={() => removeCharge(index)}>Remove</Button> : null}
                  </div>
                ))}
                <Button type="button" variant="outline" onClick={addCharge}>Add Charge Line</Button>
              </>
            )}

            {normalizedForm.cargo_type === "DANGEROUS_GOODS" ? (
              <Textarea placeholder="Dangerous goods details" value={form.dangerous_goods_details} onChange={(event) => updateField("dangerous_goods_details", event.target.value)} />
            ) : null}
            {normalizedForm.cargo_type === "PERISHABLE" ? (
              <Textarea placeholder="Perishable handling details" value={form.perishable_details} onChange={(event) => updateField("perishable_details", event.target.value)} />
            ) : null}
            <Textarea placeholder="Handling notes" value={form.handling_notes} onChange={(event) => updateField("handling_notes", event.target.value)} />
            <Textarea placeholder="Declaration notes" value={form.declaration_notes} onChange={(event) => updateField("declaration_notes", event.target.value)} />
          </CardContent>
        </Card>
      ) : null}

      {step === 4 ? (
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader><CardTitle>Review</CardTitle></CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Route</p>
                  <p className="mt-2 font-semibold text-slate-900">
                    {normalizedForm.origin_location_display || "Origin"}
                    {" -> "}
                    {normalizedForm.destination_location_display || "Destination"}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Totals</p>
                  <p className="mt-2 font-semibold text-slate-900">{totals.totalPieces} pcs | {totals.totalChargeableWeightKg} kg | {normalizedForm.currency} {totals.totalChargesAmount}</p>
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 p-4">
                <p className="font-semibold text-slate-900">{normalizedForm.shipper_company_name}</p>
                <p className="text-muted-foreground">{normalizedForm.consignee_company_name}</p>
                <p className="mt-3 text-muted-foreground">
                  {normalizedForm.cargo_description || "General Cargo"} | {formatShipmentChoice(normalizedForm.cargo_type)} | {formatShipmentChoice(normalizedForm.service_product)} | {formatShipmentChoice(normalizedForm.service_scope)}
                </p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-slate-200 bg-slate-50 shadow-sm">
            <CardHeader><CardTitle>Validation</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm">
              {[
                "Mandatory party details completed",
                "Origin and destination selected",
                `${formatShipmentChoice(normalizedForm.cargo_type)} cargo type selected`,
                `${formatShipmentChoice(normalizedForm.service_product)} product configured`,
                `${totals.totalPieces} pieces prepared for print`,
                `${totals.totalChargeableWeightKg} kg chargeable weight calculated`,
                `${normalizedForm.currency} ${totals.totalChargesAmount} total charges ready`,
              ].map((item) => (
                <div key={item} className="flex items-center gap-3 rounded-xl bg-white px-4 py-3 shadow-sm">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span>{item}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="text-sm text-muted-foreground">Step {step + 1} of {STEPS.length}</div>
        <div className="flex flex-wrap gap-3">
          <Button type="button" variant="outline" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0 || isSubmitting}>
            <ChevronLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          {step < STEPS.length - 1 ? (
            <>
              <Button type="button" variant="outline" onClick={() => persistShipment(false)} disabled={isSubmitting}>
                <Save className="mr-2 h-4 w-4" />
                Save Draft
              </Button>
              <Button type="button" onClick={goNext} disabled={isSubmitting}>
                Continue
                <ChevronRight className="ml-2 h-4 w-4" />
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={() => persistShipment(false)} disabled={isSubmitting}>
                Save Draft
              </Button>
              <Button type="button" onClick={() => persistShipment(true)} disabled={isSubmitting}>
                Finalize and Generate PDF
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
