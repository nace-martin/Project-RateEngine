import type {
  CompanySearchResult,
  Contact,
  Customer,
  LocationSearchResult,
} from "../types";
import { API_BASE_URL, getToken } from "./shared";

export async function searchCompanies(
  query: string,
): Promise<CompanySearchResult[]> {
  const url = API_BASE_URL + `/api/v3/parties/companies/search/?q=${query}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to search companies");
  }
  return response.json();
}

export async function getCompany(
  companyId: string,
): Promise<CompanySearchResult> {
  const url = API_BASE_URL + `/api/v3/customers/${companyId}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch company");
  }
  return response.json();
}

export async function getContactsForCompany(
  companyId: string,
): Promise<Contact[]> {
  const url = API_BASE_URL + `/api/v3/parties/companies/${companyId}/contacts/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch contacts");
  }
  return response.json();
}

export async function getCustomerDetail(
  customerId: string,
): Promise<Customer> {
  const url = API_BASE_URL + `/api/v3/customer-details/${customerId}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error("Failed to fetch customer details");
  }
  return response.json();
}

export async function searchLocations(
  query: string,
): Promise<LocationSearchResult[]> {
  const url =
    API_BASE_URL + `/api/v3/locations/search/?q=${encodeURIComponent(query)}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error("Failed to search locations");
  }

  return response.json();
}

export async function getLocation(
  locationId: string,
): Promise<LocationSearchResult> {
  const url = API_BASE_URL + `/api/v3/locations/${locationId}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });
  if (!response.ok) {
    throw new Error("Failed to fetch location");
  }
  return response.json();
}
