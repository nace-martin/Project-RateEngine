import type {
  CompanySearchResult,
  Contact,
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
