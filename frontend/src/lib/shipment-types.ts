import { formatPaymentTerm, formatServiceScope } from "@/lib/display";

export type ShipmentStatus = "DRAFT" | "FINALIZED" | "CANCELLED" | "REISSUED";
export type ShipmentType = "DOMESTIC" | "EXPORT" | "IMPORT";
export type ShipmentCargoType = "GENERAL_CARGO" | "VALUABLE_CARGO" | "PERISHABLE" | "LIVE_ANIMALS" | "DANGEROUS_GOODS";
export type ShipmentServiceProduct = "STANDARD" | "EXPRESS" | "DOCUMENTS" | "SMALL_PARCELS" | "CHARTER";
export type ShipmentServiceScope = "D2D" | "D2A" | "A2D" | "A2A";
export type ShipmentPaymentTerm = "PREPAID" | "COLLECT" | "THIRD_PARTY";
export type ShipmentPartyRole = "SHIPPER" | "CONSIGNEE" | "BOTH";
export type ShipmentChargeType = "FREIGHT" | "HANDLING" | "SECURITY" | "DOCUMENTATION" | "FUEL" | "OTHER";
export type ShipmentChargePaymentBy = "SHIPPER" | "CONSIGNEE" | "THIRD_PARTY";

export interface ShipmentPieceInput {
  id?: string;
  line_number?: number;
  piece_count: number;
  package_type: string;
  description: string;
  length_cm: string;
  width_cm: string;
  height_cm: string;
  gross_weight_kg: string;
  volumetric_weight_kg?: string;
  chargeable_weight_kg?: string;
}

export interface ShipmentChargeInput {
  id?: string;
  line_number?: number;
  charge_type: ShipmentChargeType;
  description: string;
  amount: string;
  currency: string;
  payment_by: ShipmentChargePaymentBy;
  notes: string;
}

export interface ShipmentRecord {
  id: string;
  status: ShipmentStatus;
  connote_number: string | null;
  shipment_type: ShipmentType;
  branch: string;
  shipment_date: string;
  reference_number: string;
  booking_reference: string;
  flight_reference: string;
  shipper_company_name: string;
  shipper_contact_name: string;
  shipper_email: string;
  shipper_phone: string;
  shipper_address_line_1: string;
  shipper_address_line_2: string;
  shipper_city: string;
  shipper_state: string;
  shipper_postal_code: string;
  shipper_country_code: string;
  consignee_company_name: string;
  consignee_contact_name: string;
  consignee_email: string;
  consignee_phone: string;
  consignee_address_line_1: string;
  consignee_address_line_2: string;
  consignee_city: string;
  consignee_state: string;
  consignee_postal_code: string;
  consignee_country_code: string;
  origin_location_id: string | null;
  destination_location_id: string | null;
  origin_location_display?: string;
  destination_location_display?: string;
  origin_code: string;
  origin_name: string;
  origin_country_code: string;
  destination_code: string;
  destination_name: string;
  destination_country_code: string;
  cargo_type: ShipmentCargoType;
  service_product: ShipmentServiceProduct;
  service_scope: ShipmentServiceScope;
  payment_term: ShipmentPaymentTerm | "THIRD_PARTY";
  export_reference: string;
  invoice_reference: string;
  permit_reference: string;
  cargo_description: string;
  is_dangerous_goods: boolean;
  dangerous_goods_details: string;
  is_perishable: boolean;
  perishable_details: string;
  handling_notes: string;
  declaration_notes: string;
  customs_notes: string;
  declared_value: string | null;
  currency: string;
  total_pieces: number;
  total_gross_weight_kg: string;
  total_volumetric_weight_kg: string;
  total_chargeable_weight_kg: string;
  total_charges_amount: string;
  pieces: ShipmentPieceInput[];
  charges: ShipmentChargeInput[];
  documents: ShipmentDocument[];
  events: ShipmentEvent[];
  source_shipment_id?: string | null;
  reissued_from_id?: string | null;
  cancelled_reason: string;
  finalized_at?: string | null;
  cancelled_at?: string | null;
  last_pdf_generated_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ShipmentDocument {
  id: string;
  document_type: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  download_url?: string | null;
}

export interface ShipmentEvent {
  id: string;
  event_type: string;
  description: string;
  metadata: Record<string, unknown>;
  created_by_username?: string | null;
  created_at: string;
}

export interface ShipmentAddressBookEntry {
  id: string;
  company_id?: string | null;
  contact_id?: string | null;
  label: string;
  party_role: ShipmentPartyRole;
  company_name: string;
  contact_name: string;
  email: string;
  phone: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  postal_code: string;
  country_code: string;
  notes: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ShipmentTemplate {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  shipper_defaults: Partial<ShipmentFormData>;
  consignee_defaults: Partial<ShipmentFormData>;
  shipment_defaults: Partial<ShipmentFormData>;
  pieces_defaults: ShipmentPieceInput[];
  charges_defaults: ShipmentChargeInput[];
  created_at: string;
  updated_at: string;
}

export interface ShipmentSettings {
  connote_station_code: string;
  connote_mode_code: string;
  default_disclaimer: string;
  updated_at: string;
}

export interface ShipmentFormData {
  shipment_type: ShipmentType;
  branch: string;
  shipment_date: string;
  reference_number: string;
  booking_reference: string;
  flight_reference: string;
  shipper_company_name: string;
  shipper_contact_name: string;
  shipper_email: string;
  shipper_phone: string;
  shipper_address_line_1: string;
  shipper_address_line_2: string;
  shipper_city: string;
  shipper_state: string;
  shipper_postal_code: string;
  shipper_country_code: string;
  consignee_company_name: string;
  consignee_contact_name: string;
  consignee_email: string;
  consignee_phone: string;
  consignee_address_line_1: string;
  consignee_address_line_2: string;
  consignee_city: string;
  consignee_state: string;
  consignee_postal_code: string;
  consignee_country_code: string;
  origin_location_id: string | null;
  destination_location_id: string | null;
  origin_code: string;
  destination_code: string;
  origin_country_code: string;
  destination_country_code: string;
  origin_location_display: string;
  destination_location_display: string;
  cargo_type: ShipmentCargoType;
  service_product: ShipmentServiceProduct;
  service_scope: ShipmentServiceScope;
  payment_term: ShipmentPaymentTerm;
  export_reference: string;
  invoice_reference: string;
  permit_reference: string;
  cargo_description: string;
  dangerous_goods_details: string;
  perishable_details: string;
  handling_notes: string;
  declaration_notes: string;
  customs_notes: string;
  pieces: ShipmentPieceInput[];
}

export const SHIPMENT_TYPE_OPTIONS: Array<{ value: Extract<ShipmentType, "DOMESTIC" | "EXPORT">; label: string }> = [
  { value: "DOMESTIC", label: "Domestic" },
  { value: "EXPORT", label: "Export" },
];

export const SHIPMENT_CARGO_TYPE_OPTIONS: Array<{ value: ShipmentCargoType; label: string }> = [
  { value: "GENERAL_CARGO", label: "General Cargo" },
  { value: "VALUABLE_CARGO", label: "Valuable Cargo" },
  { value: "PERISHABLE", label: "Perishable" },
  { value: "LIVE_ANIMALS", label: "Live Animals" },
  { value: "DANGEROUS_GOODS", label: "Dangerous Goods" },
];

export const SHIPMENT_SERVICE_PRODUCT_OPTIONS: Array<{ value: ShipmentServiceProduct; label: string }> = [
  { value: "STANDARD", label: "Standard" },
  { value: "EXPRESS", label: "Express" },
  { value: "DOCUMENTS", label: "Documents" },
  { value: "SMALL_PARCELS", label: "Small Parcels" },
  { value: "CHARTER", label: "Charter" },
];

export const SHIPMENT_PAYMENT_TYPE_OPTIONS: Array<{ value: Exclude<ShipmentPaymentTerm, "THIRD_PARTY">; label: string }> = [
  { value: "PREPAID", label: "Prepaid" },
  { value: "COLLECT", label: "Collect" },
];

export const DOMESTIC_COUNTRY_CODE = "PG";

export const createEmptyShipmentForm = (): ShipmentFormData => ({
  shipment_type: "DOMESTIC",
  branch: "",
  shipment_date: new Date().toISOString().slice(0, 10),
  reference_number: "",
  booking_reference: "",
  flight_reference: "",
  shipper_company_name: "",
  shipper_contact_name: "",
  shipper_email: "",
  shipper_phone: "",
  shipper_address_line_1: "",
  shipper_address_line_2: "",
  shipper_city: "",
  shipper_state: "",
  shipper_postal_code: "",
  shipper_country_code: "",
  consignee_company_name: "",
  consignee_contact_name: "",
  consignee_email: "",
  consignee_phone: "",
  consignee_address_line_1: "",
  consignee_address_line_2: "",
  consignee_city: "",
  consignee_state: "",
  consignee_postal_code: "",
  consignee_country_code: "",
  origin_location_id: null,
  destination_location_id: null,
  origin_code: "",
  destination_code: "",
  origin_country_code: "",
  destination_country_code: "",
  origin_location_display: "",
  destination_location_display: "",
  cargo_type: "GENERAL_CARGO",
  service_product: "STANDARD",
  service_scope: "A2A",
  payment_term: "PREPAID",
  export_reference: "",
  invoice_reference: "",
  permit_reference: "",
  cargo_description: "",
  dangerous_goods_details: "",
  perishable_details: "",
  handling_notes: "",
  declaration_notes: "",
  customs_notes: "",
  pieces: [
    {
      piece_count: 1,
      package_type: "",
      description: "",
      length_cm: "",
      width_cm: "",
      height_cm: "",
      gross_weight_kg: "",
    },
  ],
});

const toNumber = (value: string | number | undefined | null): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const formatShipmentChoice = (value: string | null | undefined): string => {
  const normalized = (value || "").toUpperCase().trim();
  if (!normalized) {
    return "";
  }

  if (["D2D", "D2A", "A2D", "A2A", "P2P"].includes(normalized)) {
    return formatServiceScope(normalized);
  }

  if (["PREPAID", "COLLECT", "THIRD_PARTY"].includes(normalized)) {
    return formatPaymentTerm(normalized);
  }

  return normalized.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
};

export const isDomesticShipmentRoute = (originCountryCode: string, destinationCountryCode: string): boolean =>
  originCountryCode === DOMESTIC_COUNTRY_CODE && destinationCountryCode === DOMESTIC_COUNTRY_CODE;

export const isExportShipmentRoute = (originCountryCode: string, destinationCountryCode: string): boolean =>
  originCountryCode === DOMESTIC_COUNTRY_CODE && Boolean(destinationCountryCode) && destinationCountryCode !== DOMESTIC_COUNTRY_CODE;

export const calculatePieceMetrics = (piece: ShipmentPieceInput) => {
  const pieceCount = Math.max(0, toNumber(piece.piece_count));
  const gross = pieceCount * toNumber(piece.gross_weight_kg);
  const volumetric = pieceCount * toNumber(piece.length_cm) * toNumber(piece.width_cm) * toNumber(piece.height_cm) / 6000;
  const chargeable = Math.max(gross, volumetric);
  return {
    gross,
    volumetric,
    chargeable,
  };
};

export const calculateShipmentTotals = (form: ShipmentFormData) => {
  const totals = form.pieces.reduce(
    (acc, piece) => {
      const metrics = calculatePieceMetrics(piece);
      acc.totalPieces += toNumber(piece.piece_count);
      acc.gross += metrics.gross;
      acc.volumetric += metrics.volumetric;
      acc.chargeable += metrics.chargeable;
      return acc;
    },
    { totalPieces: 0, gross: 0, volumetric: 0, chargeable: 0 },
  );

  return {
    totalPieces: totals.totalPieces,
    totalGrossWeightKg: totals.gross.toFixed(2),
    totalVolumetricWeightKg: totals.volumetric.toFixed(2),
    totalChargeableWeightKg: totals.chargeable.toFixed(2),
  };
};

export const normalizeShipmentForm = (form: ShipmentFormData): ShipmentFormData => ({
  ...form,
  branch: form.branch.trim(),
  reference_number: form.reference_number.trim(),
  booking_reference: form.booking_reference.trim(),
  flight_reference: form.flight_reference.trim(),
  export_reference: form.export_reference.trim(),
  invoice_reference: form.invoice_reference.trim(),
  permit_reference: form.permit_reference.trim(),
  cargo_description: form.cargo_description.trim(),
  dangerous_goods_details: form.dangerous_goods_details.trim(),
  perishable_details: form.perishable_details.trim(),
  handling_notes: form.handling_notes.trim(),
  declaration_notes: form.declaration_notes.trim(),
  customs_notes: form.customs_notes.trim(),
});

export const toShipmentPayload = (form: ShipmentFormData) => ({
  shipment_type: form.shipment_type,
  branch: form.branch,
  shipment_date: form.shipment_date,
  reference_number: form.reference_number,
  booking_reference: form.booking_reference,
  flight_reference: form.flight_reference,
  shipper_company_name: form.shipper_company_name,
  shipper_contact_name: form.shipper_contact_name,
  shipper_email: form.shipper_email,
  shipper_phone: form.shipper_phone,
  shipper_address_line_1: form.shipper_address_line_1,
  shipper_address_line_2: form.shipper_address_line_2,
  shipper_city: form.shipper_city,
  shipper_state: form.shipper_state,
  shipper_postal_code: form.shipper_postal_code,
  shipper_country_code: form.shipper_country_code,
  consignee_company_name: form.consignee_company_name,
  consignee_contact_name: form.consignee_contact_name,
  consignee_email: form.consignee_email,
  consignee_phone: form.consignee_phone,
  consignee_address_line_1: form.consignee_address_line_1,
  consignee_address_line_2: form.consignee_address_line_2,
  consignee_city: form.consignee_city,
  consignee_state: form.consignee_state,
  consignee_postal_code: form.consignee_postal_code,
  consignee_country_code: form.consignee_country_code,
  origin_location_id: form.origin_location_id,
  destination_location_id: form.destination_location_id,
  cargo_type: form.cargo_type,
  service_product: form.service_product,
  service_scope: form.service_scope,
  payment_term: form.payment_term,
  export_reference: form.export_reference,
  invoice_reference: form.invoice_reference,
  permit_reference: form.permit_reference,
  cargo_description: form.cargo_description,
  dangerous_goods_details: form.dangerous_goods_details,
  perishable_details: form.perishable_details,
  handling_notes: form.handling_notes,
  declaration_notes: form.declaration_notes,
  customs_notes: form.customs_notes,
  pieces: form.pieces,
  charges: [],
});

export const shipmentToFormData = (shipment: ShipmentRecord): ShipmentFormData => ({
  shipment_type: shipment.shipment_type,
  branch: shipment.branch || "",
  shipment_date: shipment.shipment_date,
  reference_number: shipment.reference_number,
  booking_reference: shipment.booking_reference || "",
  flight_reference: shipment.flight_reference || "",
  shipper_company_name: shipment.shipper_company_name,
  shipper_contact_name: shipment.shipper_contact_name,
  shipper_email: shipment.shipper_email,
  shipper_phone: shipment.shipper_phone,
  shipper_address_line_1: shipment.shipper_address_line_1,
  shipper_address_line_2: shipment.shipper_address_line_2,
  shipper_city: shipment.shipper_city,
  shipper_state: shipment.shipper_state,
  shipper_postal_code: shipment.shipper_postal_code,
  shipper_country_code: shipment.shipper_country_code,
  consignee_company_name: shipment.consignee_company_name,
  consignee_contact_name: shipment.consignee_contact_name,
  consignee_email: shipment.consignee_email,
  consignee_phone: shipment.consignee_phone,
  consignee_address_line_1: shipment.consignee_address_line_1,
  consignee_address_line_2: shipment.consignee_address_line_2,
  consignee_city: shipment.consignee_city,
  consignee_state: shipment.consignee_state,
  consignee_postal_code: shipment.consignee_postal_code,
  consignee_country_code: shipment.consignee_country_code,
  origin_location_id: shipment.origin_location_id,
  destination_location_id: shipment.destination_location_id,
  origin_code: shipment.origin_code,
  destination_code: shipment.destination_code,
  origin_country_code: shipment.origin_country_code,
  destination_country_code: shipment.destination_country_code,
  origin_location_display: shipment.origin_location_display || `${shipment.origin_code} ${shipment.origin_name}`.trim(),
  destination_location_display: shipment.destination_location_display || `${shipment.destination_code} ${shipment.destination_name}`.trim(),
  cargo_type: shipment.cargo_type,
  service_product: shipment.service_product,
  service_scope: shipment.service_scope,
  payment_term: shipment.payment_term,
  export_reference: shipment.export_reference || "",
  invoice_reference: shipment.invoice_reference || "",
  permit_reference: shipment.permit_reference || "",
  cargo_description: shipment.cargo_description,
  dangerous_goods_details: shipment.dangerous_goods_details,
  perishable_details: shipment.perishable_details,
  handling_notes: shipment.handling_notes,
  declaration_notes: shipment.declaration_notes,
  customs_notes: shipment.customs_notes || "",
  pieces: shipment.pieces.map((piece) => ({
    ...piece,
    length_cm: String(piece.length_cm ?? ""),
    width_cm: String(piece.width_cm ?? ""),
    height_cm: String(piece.height_cm ?? ""),
    gross_weight_kg: String(piece.gross_weight_kg ?? ""),
    volumetric_weight_kg: piece.volumetric_weight_kg ? String(piece.volumetric_weight_kg) : undefined,
    chargeable_weight_kg: piece.chargeable_weight_kg ? String(piece.chargeable_weight_kg) : undefined,
  })),
});
