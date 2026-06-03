import type {
  CreateInteractionPayload,
  Interaction,
  Opportunity,
  OpportunityPayload,
  PaginatedResponse,
  Task,
  V3QuoteComputeResponse,
} from "../types";

import {
  API_BASE_URL,
  getJson,
  sendJson,
  appendDefinedParams,
  normalizeListResponse,
} from "./shared";

export async function createInteraction(data: CreateInteractionPayload): Promise<Interaction> {
  try {
    return await sendJson(API_BASE_URL + "/api/v3/crm/interactions/", "POST", data);
  } catch (error) {
    throw new Error(`Failed to log activity: ${(error as Error).message}`);
  }
}

type ListOpportunityParams = {
  company?: string;
  status?: string;
  owner?: string;
  service_type?: string;
  priority?: string;
};

export async function listOpportunities(params: ListOpportunityParams = {}): Promise<Opportunity[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/opportunities/");
  appendDefinedParams(url, params);

  try {
    const payload = await getJson<Opportunity[] | PaginatedResponse<Opportunity>>(url.toString());
    return normalizeListResponse(payload);
  } catch (error) {
    throw new Error(`Failed to load opportunities: ${(error as Error).message}`);
  }
}

export async function getOpportunity(opportunityId: string): Promise<Opportunity> {
  try {
    return await getJson<Opportunity>(API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/`);
  } catch (error) {
    throw new Error(`Failed to load opportunity: ${(error as Error).message}`);
  }
}

export async function createOpportunity(data: OpportunityPayload): Promise<Opportunity> {
  try {
    return await sendJson<Opportunity>(API_BASE_URL + "/api/v3/crm/opportunities/", "POST", data);
  } catch (error) {
    throw new Error(`Failed to create opportunity: ${(error as Error).message}`);
  }
}

export async function updateOpportunity(
  opportunityId: string,
  data: Partial<OpportunityPayload>,
): Promise<Opportunity> {
  try {
    return await sendJson<Opportunity>(
      API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/`,
      "PATCH",
      data,
    );
  } catch (error) {
    throw new Error(`Failed to update opportunity: ${(error as Error).message}`);
  }
}

export async function markOpportunityQualified(opportunityId: string): Promise<Opportunity> {
  try {
    return await sendJson<Opportunity>(
      API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/mark_qualified/`,
      "POST",
      {},
    );
  } catch (error) {
    throw new Error(`Failed to mark opportunity as qualified: ${(error as Error).message}`);
  }
}

export async function markOpportunityWon(opportunityId: string, wonReason?: string): Promise<Opportunity> {
  try {
    return await sendJson<Opportunity>(
      API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/mark_won/`,
      "POST",
      { won_reason: wonReason },
    );
  } catch (error) {
    throw new Error(`Failed to mark opportunity as won: ${(error as Error).message}`);
  }
}

export async function markOpportunityLost(opportunityId: string, lostReason?: string): Promise<Opportunity> {
  try {
    return await sendJson<Opportunity>(
      API_BASE_URL + `/api/v3/crm/opportunities/${opportunityId}/mark_lost/`,
      "POST",
      { lost_reason: lostReason },
    );
  } catch (error) {
    throw new Error(`Failed to mark opportunity as lost: ${(error as Error).message}`);
  }
}

export async function listOpportunitiesByCompany(companyId: string): Promise<Opportunity[]> {
  return listOpportunities({ company: companyId });
}

export async function listInteractionsByCompany(companyId: string): Promise<Interaction[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/interactions/");
  url.searchParams.set("company", companyId);

  try {
    const payload = await getJson<Interaction[] | PaginatedResponse<Interaction>>(url.toString());
    return normalizeListResponse(payload);
  } catch (error) {
    throw new Error(`Failed to load activity timeline: ${(error as Error).message}`);
  }
}

export async function listRecentInteractions(): Promise<Interaction[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/interactions/");

  try {
    const payload = await getJson<Interaction[] | PaginatedResponse<Interaction>>(url.toString());
    return normalizeListResponse(payload);
  } catch (error) {
    throw new Error(`Failed to load recent activity: ${(error as Error).message}`);
  }
}

export async function listInteractionsByOpportunity(opportunityId: string): Promise<Interaction[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/interactions/");
  url.searchParams.set("opportunity", opportunityId);

  try {
    const payload = await getJson<Interaction[] | PaginatedResponse<Interaction>>(url.toString());
    return normalizeListResponse(payload);
  } catch (error) {
    throw new Error(`Failed to load activity timeline: ${(error as Error).message}`);
  }
}

type ListTaskParams = {
  owner?: string;
  status?: string;
  due_date?: string;
  company?: string;
  opportunity?: string;
};

export async function listTasks(params: ListTaskParams = {}): Promise<Task[]> {
  const url = new URL(API_BASE_URL + "/api/v3/crm/tasks/");
  appendDefinedParams(url, params);

  try {
    const payload = await getJson<Task[] | PaginatedResponse<Task>>(url.toString());
    return normalizeListResponse(payload);
  } catch (error) {
    throw new Error(`Failed to load tasks: ${(error as Error).message}`);
  }
}

export async function listTasksByOpportunity(opportunityId: string): Promise<Task[]> {
  return listTasks({ opportunity: opportunityId });
}

export async function listTasksByCompany(companyId: string): Promise<Task[]> {
  return listTasks({ company: companyId });
}

export type TaskPayload = {
  company?: string | null;
  opportunity?: string | null;
  description: string;
  owner?: number | null;
  due_date: string;
  status?: string;
};

export async function createTask(data: TaskPayload): Promise<Task> {
  try {
    return await sendJson<Task>(API_BASE_URL + "/api/v3/crm/tasks/", "POST", data);
  } catch (error) {
    throw new Error(`Failed to create task: ${(error as Error).message}`);
  }
}

export async function updateTask(taskId: string, data: Partial<TaskPayload>): Promise<Task> {
  try {
    return await sendJson<Task>(API_BASE_URL + `/api/v3/crm/tasks/${taskId}/`, "PATCH", data);
  } catch (error) {
    throw new Error(`Failed to update task: ${(error as Error).message}`);
  }
}

export async function completeTask(taskId: string): Promise<Task> {
  try {
    return await sendJson<Task>(API_BASE_URL + `/api/v3/crm/tasks/${taskId}/complete/`, "POST", {});
  } catch (error) {
    throw new Error(`Failed to complete task: ${(error as Error).message}`);
  }
}

export async function listQuotesByOpportunity(opportunityId: string): Promise<V3QuoteComputeResponse[]> {
  const url = new URL(API_BASE_URL + "/api/v3/quotes/");
  url.searchParams.set("opportunity", opportunityId);
  url.searchParams.set("is_archived", "false");

  try {
    const payload = await getJson<V3QuoteComputeResponse[] | PaginatedResponse<V3QuoteComputeResponse>>(
      url.toString(),
    );
    return normalizeListResponse(payload);
  } catch (error) {
    throw new Error(`Failed to load linked quotes: ${(error as Error).message}`);
  }
}
