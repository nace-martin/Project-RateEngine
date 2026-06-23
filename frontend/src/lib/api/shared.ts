import { API_BASE_URL } from "../config";
import type { PaginatedResponse } from "../types";

export { API_BASE_URL };

export const getToken = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("authToken");
};

export const resolveAuthToken = (tokenOverride?: string | null): string => {
  const token = tokenOverride ?? getToken();
  if (!token) {
    throw new Error("Authentication token not available. Please log in.");
  }
  return token;
};

export const parseErrorResponse = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    if (typeof data === "string") {
      return data;
    }
    if (data && typeof data === "object") {
      for (const key of ["detail", "error", "message"] as const) {
        const value = (data as Record<string, unknown>)[key];
        if (typeof value === "string") {
          return value;
        }
        if (Array.isArray(value) && typeof value[0] === "string") {
          return value[0];
        }
      }
      return JSON.stringify(data);
    }
  } catch {
    // ignore parse errors
  }
  if (response.status === 403) {
    return "You do not have permission to access this record.";
  }
  if (response.status === 404) {
    return "This record is not available to your current scope.";
  }
  return response.statusText || "Unknown error";
};

export async function getJson<T>(url: string): Promise<T> {
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

export async function sendJson<T>(url: string, method: string, data?: unknown): Promise<T> {
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

export function appendDefinedParams(url: URL, params: Record<string, string | undefined>): void {
  Object.entries(params).forEach(([key, value]) => {
    if (value) {
      url.searchParams.set(key, value);
    }
  });
}

export function normalizeListResponse<T>(payload: T[] | PaginatedResponse<T>): T[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (payload && Array.isArray(payload.results)) {
    return payload.results;
  }
  return [];
}

