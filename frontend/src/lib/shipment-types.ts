export type ShipmentStatus = "DRAFT" | "FINALIZED" | "CANCELLED" | "REISSUED";
export type ShipmentServiceLevel = "EXPRESS" | "PRIORITY" | "ECONOMY" | "CHARTER";
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
  shipment_date: string;
  reference_number: string;
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
  service_level: ShipmentServiceLevel;
  payment_term: ShipmentPaymentTerm;
  commodity_description: string;
  goods_description: string;
  is_dangerous_goods: boolean;
  dangerous_goods_details: string;
  is_perishable: boolean;
  perishable_details: string;
  handling_notes: string;
  declaration_notes: string;
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
  shipment_date: string;
  reference_number: string;
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
  origin_location_display: string;
  destination_location_display: string;
  service_level: ShipmentServiceLevel;
  payment_term: ShipmentPaymentTerm;
  commodity_description: string;
  goods_description: string;
  is_dangerous_goods: boolean;
  dangerous_goods_details: string;
  is_perishable: boolean;
  perishable_details: string;
  handling_notes: string;
  declaration_notes: string;
  declared_value: string;
  currency: string;
  pieces: ShipmentPieceInput[];
  charges: ShipmentChargeInput[];
}

export const createEmptyShipmentForm = (): ShipmentFormData => ({
  shipment_date: new Date().toISOString().slice(0, 10),
  reference_number: "",
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
  origin_location_display: "",
  destination_location_display: "",
  service_level: "EXPRESS",
  payment_term: "PREPAID",
  commodity_description: "",
  goods_description: "",
  is_dangerous_goods: false,
  dangerous_goods_details: "",
  is_perishable: false,
  perishable_details: "",
  handling_notes: "",
  declaration_notes: "",
  declared_value: "",
  currency: "PGK",
  pieces: [
    {
      piece_count: 1,
      package_type: "CTN",
      description: "",
      length_cm: "",
      width_cm: "",
      height_cm: "",
      gross_weight_kg: "",
    },
  ],
  charges: [
    {
      charge_type: "FREIGHT",
      description: "Air freight",
      amount: "",
      currency: "PGK",
      payment_by: "SHIPPER",
      notes: "",
    },
  ],
});

const toNumber = (value: string | number | undefined | null): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

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

  const totalChargesAmount = form.charges.reduce((sum, charge) => sum + toNumber(charge.amount), 0);
  return {
    totalPieces: totals.totalPieces,
    totalGrossWeightKg: totals.gross.toFixed(2),
    totalVolumetricWeightKg: totals.volumetric.toFixed(2),
    totalChargeableWeightKg: totals.chargeable.toFixed(2),
    totalChargesAmount: totalChargesAmount.toFixed(2),
  };
};

export const toShipmentPayload = (form: ShipmentFormData) => ({
  shipment_date: form.shipment_date,
  reference_number: form.reference_number,
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
  service_level: form.service_level,
  payment_term: form.payment_term,
  commodity_description: form.commodity_description,
  goods_description: form.goods_description,
  is_dangerous_goods: form.is_dangerous_goods,
  dangerous_goods_details: form.dangerous_goods_details,
  is_perishable: form.is_perishable,
  perishable_details: form.perishable_details,
  handling_notes: form.handling_notes,
  declaration_notes: form.declaration_notes,
  declared_value: form.declared_value || null,
  currency: form.currency,
  pieces: form.pieces,
  charges: form.charges,
});

export const shipmentToFormData = (shipment: ShipmentRecord): ShipmentFormData => ({
  shipment_date: shipment.shipment_date,
  reference_number: shipment.reference_number,
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
  origin_location_display: shipment.origin_location_display || `${shipment.origin_code} ${shipment.origin_name}`.trim(),
  destination_location_display: shipment.destination_location_display || `${shipment.destination_code} ${shipment.destination_name}`.trim(),
  service_level: shipment.service_level,
  payment_term: shipment.payment_term,
  commodity_description: shipment.commodity_description,
  goods_description: shipment.goods_description,
  is_dangerous_goods: shipment.is_dangerous_goods,
  dangerous_goods_details: shipment.dangerous_goods_details,
  is_perishable: shipment.is_perishable,
  perishable_details: shipment.perishable_details,
  handling_notes: shipment.handling_notes,
  declaration_notes: shipment.declaration_notes,
  declared_value: shipment.declared_value || "",
  currency: shipment.currency,
  pieces: shipment.pieces.map((piece) => ({
    ...piece,
    length_cm: String(piece.length_cm ?? ""),
    width_cm: String(piece.width_cm ?? ""),
    height_cm: String(piece.height_cm ?? ""),
    gross_weight_kg: String(piece.gross_weight_kg ?? ""),
    volumetric_weight_kg: piece.volumetric_weight_kg ? String(piece.volumetric_weight_kg) : undefined,
    chargeable_weight_kg: piece.chargeable_weight_kg ? String(piece.chargeable_weight_kg) : undefined,
  })),
  charges: shipment.charges.map((charge) => ({
    ...charge,
    amount: String(charge.amount ?? ""),
  })),
});
