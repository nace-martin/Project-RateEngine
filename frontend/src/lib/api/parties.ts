import type {
  CompanySearchResult,
  Contact,
  Customer,
  LocationSearchResult,
} from "../types";
import { API_BASE_URL, getJson } from "./shared";

export async function searchCompanies(query: string): Promise<CompanySearchResult[]> {
  try {
    return await getJson<CompanySearchResult[]>(
      API_BASE_URL + `/api/v3/parties/companies/search/?q=${encodeURIComponent(query)}`,
    );
  } catch {
    throw new Error("Failed to search companies");
  }
}

export async function getCompany(companyId: string): Promise<CompanySearchResult> {
  try {
    return await getJson<CompanySearchResult>(API_BASE_URL + `/api/v3/customers/${companyId}/`);
  } catch {
    throw new Error("Failed to fetch company");
  }
}

export async function listCustomers(): Promise<CompanySearchResult[]> {
  try {
    const payload = await getJson<CompanySearchResult[] | { results?: CompanySearchResult[] }>(
      API_BASE_URL + "/api/v3/customers/",
    );
    return Array.isArray(payload) ? payload : payload.results || [];
  } catch {
    throw new Error("Failed to fetch customers");
  }
}

export async function getContactsForCompany(companyId: string): Promise<Contact[]> {
  try {
    return await getJson<Contact[]>(API_BASE_URL + `/api/v3/parties/companies/${companyId}/contacts/`);
  } catch {
    throw new Error("Failed to fetch contacts");
  }
}

export async function getCustomerDetail(customerId: string): Promise<Customer> {
  try {
    return await getJson<Customer>(API_BASE_URL + `/api/v3/customer-details/${customerId}/`);
  } catch {
    throw new Error("Failed to fetch customer details");
  }
}

export async function searchLocations(query: string): Promise<LocationSearchResult[]> {
  try {
    return await getJson<LocationSearchResult[]>(
      API_BASE_URL + `/api/v3/locations/search/?q=${encodeURIComponent(query)}`,
    );
  } catch {
    throw new Error("Failed to search locations");
  }
}

export async function getLocation(locationId: string): Promise<LocationSearchResult> {
  try {
    return await getJson<LocationSearchResult>(API_BASE_URL + `/api/v3/locations/${locationId}/`);
  } catch {
    throw new Error("Failed to fetch location");
  }
}
