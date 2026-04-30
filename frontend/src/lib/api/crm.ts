import type {
  CompanySearchResult,
  CreateInteractionPayload,
  Interaction,
  Opportunity,
  PaginatedResponse,
} from "../types";
import { searchCompanies as searchPartyCompanies } from "./parties";
import { API_BASE_URL, parseErrorResponse, resolveAuthToken } from "./shared";

function normalizeListResponse<T>(payload: T[] | PaginatedResponse<T>): T[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (payload && Array.isArray(payload.results)) {
    return payload.results;
  }
  return [];
}

export async function createInteraction(data: CreateInteractionPayload): Promise<Interaction> {
  const response = await fetch(API_BASE_URL + "/api/v3/crm/interactions/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to log activity: ${detail}`);
  }

  return response.json();
}

export async function searchCompanies(query: string): Promise<CompanySearchResult[]> {
  return searchPartyCompanies(query);
}

export async function listOpportunitiesByCompany(companyId: string): Promise<Opportunity[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/opportunities/");
  url.searchParams.set("company", companyId);

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to load opportunities: ${detail}`);
  }

  const payload = (await response.json()) as Opportunity[] | PaginatedResponse<Opportunity>;
  return normalizeListResponse(payload);
}

export async function listInteractionsByCompany(companyId: string): Promise<Interaction[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/interactions/");
  url.searchParams.set("company", companyId);

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to load activity timeline: ${detail}`);
  }

  const payload = (await response.json()) as Interaction[] | PaginatedResponse<Interaction>;
  return normalizeListResponse(payload);
}
