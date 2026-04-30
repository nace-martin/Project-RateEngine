import type {
  CompanySearchResult,
  CreateInteractionPayload,
  Interaction,
  Opportunity,
  OpportunityPayload,
  PaginatedResponse,
  Task,
  V3QuoteComputeResponse,
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

type ListOpportunityParams = {
  company?: string;
  status?: string;
  owner?: string;
  service_type?: string;
  priority?: string;
};

function appendDefinedParams(url: URL, params: Record<string, string | undefined>) {
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    }
  });
}

export async function listOpportunities(params: ListOpportunityParams = {}): Promise<Opportunity[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/opportunities/");
  appendDefinedParams(url, params);

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

export async function getOpportunity(opportunityId: string): Promise<Opportunity> {
  const response = await fetch(API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/`, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to load opportunity: ${detail}`);
  }

  return response.json();
}

export async function createOpportunity(data: OpportunityPayload): Promise<Opportunity> {
  const response = await fetch(API_BASE_URL + "/api/v3/crm/opportunities/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create opportunity: ${detail}`);
  }

  return response.json();
}

export async function updateOpportunity(
  opportunityId: string,
  data: Partial<OpportunityPayload>,
): Promise<Opportunity> {
  const response = await fetch(API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update opportunity: ${detail}`);
  }

  return response.json();
}

export async function listOpportunitiesByCompany(companyId: string): Promise<Opportunity[]> {
  return listOpportunities({ company: companyId });
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

export async function listInteractionsByOpportunity(opportunityId: string): Promise<Interaction[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/interactions/");
  url.searchParams.set("opportunity", opportunityId);

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

export async function listTasksByOpportunity(opportunityId: string): Promise<Task[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/tasks/");
  url.searchParams.set("opportunity", opportunityId);

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to load tasks: ${detail}`);
  }

  const payload = (await response.json()) as Task[] | PaginatedResponse<Task>;
  return normalizeListResponse(payload);
}

export async function listQuotesByOpportunity(opportunityId: string): Promise<V3QuoteComputeResponse[]> {
  const url = new URL(API_BASE_URL + "/api/v3/quotes/");
  url.searchParams.set("opportunity", opportunityId);
  url.searchParams.set("is_archived", "false");

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to load linked quotes: ${detail}`);
  }

  const payload = (await response.json()) as V3QuoteComputeResponse[] | PaginatedResponse<V3QuoteComputeResponse>;
  return normalizeListResponse(payload);
}
