"use client";

import type {
  ShipmentAddressBookEntry,
  ShipmentFormData,
  ShipmentServiceScope,
} from "@/lib/shipment-types";
import type { LocationSearchResult } from "@/lib/types";

export type ShipmentWizardStepProps = {
  form: ShipmentFormData;
  updateField: <K extends keyof ShipmentFormData>(field: K, value: ShipmentFormData[K]) => void;
};

export type ShipmentTypeStepProps = ShipmentWizardStepProps;

export type ShipmentPartiesStepProps = ShipmentWizardStepProps & {
  addressBookEntries: ShipmentAddressBookEntry[];
  applyAddressBookEntry: (entryId: string, role: "shipper" | "consignee") => void;
};

export type ShipmentDetailsStepProps = ShipmentWizardStepProps & {
  handleLocationSelect: (field: "origin" | "destination", location: LocationSearchResult | null) => void;
  serviceScopeOptions: ReadonlyArray<{ value: ShipmentServiceScope; label: string }>;
};

export type ShipmentCargoStepProps = ShipmentWizardStepProps & {
  normalizedForm: ShipmentFormData;
  totals: {
    totalPieces: number;
    totalGrossWeightKg: string;
    totalChargeableWeightKg: string;
  };
  updatePiece: (index: number, field: keyof ShipmentFormData["pieces"][number], value: string | number) => void;
  addPiece: () => void;
  removePiece: (index: number) => void;
};

export type ShipmentReviewStepProps = {
  normalizedForm: ShipmentFormData;
  totals: {
    totalPieces: number;
    totalChargeableWeightKg: string;
  };
};
