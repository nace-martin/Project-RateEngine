import {
  ShipmentAddressBookEntry,
  ShipmentRecord,
  ShipmentSettings,
  ShipmentTemplate,
} from "../shipment-types";
import { API_BASE_URL, parseErrorResponse, resolveAuthToken } from "./shared";

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(detail);
  }
  return response.json();
}

async function sendJson<T>(url: string, method: string, data?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

export async function listShipments(params?: { q?: string; status?: string }): Promise<ShipmentRecord[]> {
  const url = new URL(API_BASE_URL + "/api/v3/shipments/");
  if (params?.q) url.searchParams.append("q", params.q);
  if (params?.status) url.searchParams.append("status", params.status);
  return getJson<ShipmentRecord[]>(url.toString());
}

export async function getShipment(id: string): Promise<ShipmentRecord> {
  return getJson<ShipmentRecord>(API_BASE_URL + `/api/v3/shipments/${id}/`);
}

export async function createShipment(payload: unknown): Promise<ShipmentRecord> {
  return sendJson<ShipmentRecord>(API_BASE_URL + "/api/v3/shipments/", "POST", payload);
}

export async function updateShipment(id: string, payload: unknown): Promise<ShipmentRecord> {
  return sendJson<ShipmentRecord>(API_BASE_URL + `/api/v3/shipments/${id}/`, "PATCH", payload);
}

export async function finalizeShipment(id: string, payload?: unknown): Promise<ShipmentRecord> {
  return sendJson<ShipmentRecord>(API_BASE_URL + `/api/v3/shipments/${id}/finalize/`, "POST", payload ?? {});
}

export async function duplicateShipment(id: string): Promise<ShipmentRecord> {
  return sendJson<ShipmentRecord>(API_BASE_URL + `/api/v3/shipments/${id}/duplicate/`, "POST", {});
}

export async function cancelShipment(id: string, reason: string): Promise<ShipmentRecord> {
  return sendJson<ShipmentRecord>(API_BASE_URL + `/api/v3/shipments/${id}/cancel/`, "POST", { reason });
}

export async function reissueShipment(id: string): Promise<ShipmentRecord> {
  return sendJson<ShipmentRecord>(API_BASE_URL + `/api/v3/shipments/${id}/reissue/`, "POST", {});
}

export async function openShipmentPdf(id: string): Promise<void> {
  const response = await fetch(API_BASE_URL + `/api/v3/shipments/${id}/pdf/`, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(detail);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  window.open(objectUrl, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
}

export async function listShipmentAddressBook(partyRole?: string): Promise<ShipmentAddressBookEntry[]> {
  const url = new URL(API_BASE_URL + "/api/v3/shipments/address-book/");
  if (partyRole) url.searchParams.append("party_role", partyRole);
  return getJson<ShipmentAddressBookEntry[]>(url.toString());
}

export async function createShipmentAddressBookEntry(payload: Partial<ShipmentAddressBookEntry>): Promise<ShipmentAddressBookEntry> {
  return sendJson<ShipmentAddressBookEntry>(API_BASE_URL + "/api/v3/shipments/address-book/", "POST", payload);
}

export async function updateShipmentAddressBookEntry(id: string, payload: Partial<ShipmentAddressBookEntry>): Promise<ShipmentAddressBookEntry> {
  return sendJson<ShipmentAddressBookEntry>(API_BASE_URL + `/api/v3/shipments/address-book/${id}/`, "PATCH", payload);
}

export async function deleteShipmentAddressBookEntry(id: string): Promise<void> {
  await sendJson<void>(API_BASE_URL + `/api/v3/shipments/address-book/${id}/`, "DELETE");
}

export async function listShipmentTemplates(): Promise<ShipmentTemplate[]> {
  return getJson<ShipmentTemplate[]>(API_BASE_URL + "/api/v3/shipments/templates/");
}

export async function createShipmentTemplate(payload: Partial<ShipmentTemplate>): Promise<ShipmentTemplate> {
  return sendJson<ShipmentTemplate>(API_BASE_URL + "/api/v3/shipments/templates/", "POST", payload);
}

export async function updateShipmentTemplate(id: string, payload: Partial<ShipmentTemplate>): Promise<ShipmentTemplate> {
  return sendJson<ShipmentTemplate>(API_BASE_URL + `/api/v3/shipments/templates/${id}/`, "PATCH", payload);
}

export async function deleteShipmentTemplate(id: string): Promise<void> {
  await sendJson<void>(API_BASE_URL + `/api/v3/shipments/templates/${id}/`, "DELETE");
}

export async function getShipmentSettings(): Promise<ShipmentSettings> {
  return getJson<ShipmentSettings>(API_BASE_URL + "/api/v3/shipments/settings/");
}

export async function updateShipmentSettings(payload: Partial<ShipmentSettings>): Promise<ShipmentSettings> {
  return sendJson<ShipmentSettings>(API_BASE_URL + "/api/v3/shipments/settings/", "PATCH", payload);
}
