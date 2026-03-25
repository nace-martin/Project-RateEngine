"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useToast } from "@/context/toast-context";
import { useConfirm } from "@/hooks/useConfirm";
import { useReturnTo } from "@/hooks/useReturnTo";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import {
  createShipment,
  finalizeShipment,
  openShipmentPdf,
  updateShipment,
} from "@/lib/api/shipments";
import type { LocationSearchResult } from "@/lib/types";
import {
  calculateShipmentTotals,
  createEmptyShipmentForm,
  isDomesticShipmentRoute,
  isExportShipmentRoute,
  normalizeShipmentForm,
  ShipmentAddressBookEntry,
  ShipmentFormData,
  ShipmentRecord,
  ShipmentTemplate,
  shipmentToFormData,
  toShipmentPayload,
} from "@/lib/shipment-types";

export function useShipmentWizard({
  shipmentId,
  initialShipment,
  templates,
  addressBookEntries,
}: {
  shipmentId?: string;
  initialShipment?: ShipmentRecord | null;
  templates: ShipmentTemplate[];
  addressBookEntries: ShipmentAddressBookEntry[];
}) {
  const router = useRouter();
  const { toast } = useToast();
  const confirm = useConfirm();
  const returnTo = useReturnTo();

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<ShipmentFormData>(createEmptyShipmentForm());
  const [activeShipmentId, setActiveShipmentId] = useState<string | undefined>(shipmentId || initialShipment?.id || undefined);
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [stepErrors, setStepErrors] = useState<string[]>([]);
  const [activeAction, setActiveAction] = useState<"draft" | "finalize" | null>(null);
  const [initialSnapshot, setInitialSnapshot] = useState(() => JSON.stringify(normalizeShipmentForm(createEmptyShipmentForm())));

  useEffect(() => {
    if (initialShipment) {
      const seededForm = shipmentToFormData(initialShipment);
      setForm(seededForm);
      setInitialSnapshot(JSON.stringify(normalizeShipmentForm(seededForm)));
    }
  }, [initialShipment]);

  useEffect(() => {
    setActiveShipmentId(shipmentId || initialShipment?.id || undefined);
  }, [initialShipment?.id, shipmentId]);

  const normalizedForm = useMemo(() => normalizeShipmentForm(form), [form]);
  const totals = useMemo(() => calculateShipmentTotals(normalizedForm), [normalizedForm]);
  const isDirty = JSON.stringify(normalizedForm) !== initialSnapshot;
  useUnsavedChangesGuard(isDirty, "You have unsaved shipment changes. Leave this workflow?");

  const confirmLeave = async () => {
    if (!isDirty) {
      return true;
    }
    return confirm({
      title: "Discard shipment changes?",
      description: "You have unsaved shipment changes. Leaving now will discard them.",
      confirmLabel: "Discard changes",
      cancelLabel: "Stay here",
      variant: "destructive",
    });
  };

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

  const addPiece = () => {
    setForm((current) => ({
      ...current,
      pieces: [
        ...current.pieces,
        { piece_count: 1, package_type: "", description: "", length_cm: "", width_cm: "", height_cm: "", gross_weight_kg: "" },
      ],
    }));
  };

  const removePiece = (index: number) => {
    setForm((current) => ({
      ...current,
      pieces: current.pieces.filter((_, pieceIndex) => pieceIndex !== index),
    }));
  };

  const hasStartedPiece = (piece: ShipmentFormData["pieces"][number]) =>
    Number(piece.piece_count) > 1
    || [piece.package_type, piece.description, piece.length_cm, piece.width_cm, piece.height_cm, piece.gross_weight_kg]
      .some((value) => Boolean(String(value ?? "").trim()));

  const isCompletePiece = (piece: ShipmentFormData["pieces"][number]) =>
    Number(piece.piece_count) > 0
    && Number(piece.length_cm) > 0
    && Number(piece.width_cm) > 0
    && Number(piece.height_cm) > 0
    && Number(piece.gross_weight_kg) > 0;

  const getIncompletePieceErrors = () =>
    normalizedForm.pieces.flatMap((piece, pieceIndex) => (
      hasStartedPiece(piece) && !isCompletePiece(piece)
        ? [`Cargo line ${pieceIndex + 1} is incomplete.`]
        : []
    ));

  const validateStep = (index: number) => {
    const errors: string[] = [];

    if (index === 0) {
      if (!normalizedForm.shipment_type) {
        errors.push("Select a shipment type.");
      }
      if (!normalizedForm.branch) {
        errors.push("Branch is required.");
      }
      if (!normalizedForm.shipment_date) {
        errors.push("Shipment date is required.");
      }
    }

    if (index === 1) {
      if (!normalizedForm.shipper_company_name || !normalizedForm.shipper_address_line_1 || !normalizedForm.shipper_city || !normalizedForm.shipper_country_code) {
        errors.push("Complete mandatory shipper details.");
      }
      if (!normalizedForm.consignee_company_name || !normalizedForm.consignee_address_line_1 || !normalizedForm.consignee_city || !normalizedForm.consignee_country_code) {
        errors.push("Complete mandatory consignee details.");
      }
    }

    if (index === 2) {
      if (!normalizedForm.origin_location_id || !normalizedForm.destination_location_id) {
        errors.push("Origin and destination are required.");
      }
      if (normalizedForm.shipment_type === "DOMESTIC" && !isDomesticShipmentRoute(normalizedForm.origin_country_code, normalizedForm.destination_country_code)) {
        errors.push("Domestic shipments must stay within Papua New Guinea.");
      }
      if (normalizedForm.shipment_type === "EXPORT" && !isExportShipmentRoute(normalizedForm.origin_country_code, normalizedForm.destination_country_code)) {
        errors.push("Export shipments must depart Papua New Guinea for an overseas destination.");
      }
      if (!normalizedForm.payment_term) {
        errors.push("Payment type is required.");
      }
    }

    if (index === 3) {
      const completePieces = normalizedForm.pieces.filter(isCompletePiece);
      if (!completePieces.length) {
        errors.push("Add at least one complete cargo piece.");
      }
      errors.push(...getIncompletePieceErrors());
      if (normalizedForm.cargo_type === "DANGEROUS_GOODS" && !normalizedForm.dangerous_goods_details) {
        errors.push("Dangerous goods details are required.");
      }
      if (normalizedForm.cargo_type === "PERISHABLE" && !normalizedForm.perishable_details) {
        errors.push("Perishable handling details are required.");
      }
    }

    return errors;
  };

  const buildPayload = (finalize: boolean) => {
    const completePieces = normalizedForm.pieces.filter(isCompletePiece);
    return toShipmentPayload({
      ...normalizedForm,
      pieces: finalize ? normalizedForm.pieces : completePieces,
    });
  };

  const persistAction = useAsyncAction(
    async ({ finalize, validateBeforeSave }: { finalize: boolean; validateBeforeSave: boolean }) => {
      if (validateBeforeSave) {
        const validationErrors = finalize
          ? Array.from(new Set([0, 1, 2, 3].flatMap((stepIndex) => validateStep(stepIndex))))
          : validateStep(step);
        setStepErrors(validationErrors);
        if (validationErrors.length) {
          if (finalize) {
            const firstFailingStep = [0, 1, 2, 3].find((stepIndex) => validateStep(stepIndex).length > 0);
            if (typeof firstFailingStep === "number") {
              setStep(firstFailingStep);
            }
          }
          throw new Error("Validation failed");
        }
      } else {
        const incompletePieceErrors = getIncompletePieceErrors();
        setStepErrors(incompletePieceErrors);
        if (incompletePieceErrors.length) {
          setStep(3);
          throw new Error("Incomplete cargo lines");
        }
      }

      setActiveAction(finalize ? "finalize" : "draft");
      const payload = buildPayload(finalize);
      const targetShipmentId = activeShipmentId || shipmentId || initialShipment?.id;
      const saved = targetShipmentId ? await updateShipment(targetShipmentId, payload) : await createShipment(payload);

      if (!targetShipmentId) {
        setActiveShipmentId(saved.id);
        window.history.replaceState(window.history.state, "", `/shipments/new?shipmentId=${saved.id}`);
      }

      if (finalize) {
        const finalized = await finalizeShipment(saved.id, payload);
        await openShipmentPdf(finalized.id);
        return { saved, finalized };
      }

      return { saved };
    },
    {
      onSuccess: async (result) => {
        setInitialSnapshot(JSON.stringify(normalizedForm));
        if ("finalized" in result && result.finalized) {
          toast({ title: "Shipment finalized", description: `Connote ${result.finalized.connote_number} generated.`, variant: "success" });
          router.push(`/shipments/${result.finalized.id}`);
          return;
        }
        toast({ title: "Draft saved", description: "Shipment draft saved successfully.", variant: "success" });
        router.push(`/shipments/${result.saved.id}`);
      },
      onError: async (error) => {
        if (error.message === "Validation failed") {
          toast({
            title: "Review required fields",
            description: "Fix the highlighted shipment details before continuing.",
            variant: "destructive",
          });
          return;
        }
        if (error.message === "Incomplete cargo lines") {
          toast({
            title: "Complete or remove partial cargo lines",
            description: "Finish any started cargo rows before saving this draft so no shipment details are lost.",
            variant: "destructive",
          });
          return;
        }
        toast({
          title: "Unable to save shipment",
          description: error.message,
          variant: "destructive",
        });
      },
    },
  );

  const goNext = () => {
    const errors = validateStep(step);
    setStepErrors(errors);
    if (errors.length) {
      toast({
        title: "Review this step",
        description: "Complete the required shipment details before moving on.",
        variant: "destructive",
      });
      return;
    }
    setStep((current) => Math.min(current + 1, 4));
  };

  return {
    step,
    setStep,
    form,
    normalizedForm,
    totals,
    selectedTemplateId,
    setSelectedTemplateId,
    stepErrors,
    activeAction,
    isSubmitting: persistAction.isRunning,
    isDirty,
    returnTo,
    confirmLeave,
    updateField,
    applyTemplate,
    applyAddressBookEntry,
    handleLocationSelect,
    updatePiece,
    addPiece,
    removePiece,
    goNext,
    canContinue: validateStep(step).length === 0,
    canFinalize: [0, 1, 2, 3].every((stepIndex) => validateStep(stepIndex).length === 0),
    persistShipment: async (options: { finalize: boolean; validateBeforeSave: boolean }) => {
      try {
        await persistAction.run(options);
      } catch {
        return;
      } finally {
        setActiveAction(null);
      }
    },
    handleCancel: async () => {
      if (!await confirmLeave()) {
        return;
      }
      router.push(returnTo || "/shipments");
    },
  };
}
