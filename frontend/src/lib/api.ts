import {
  LoginData,
  User,
  Customer,
  RatecardFile,
  CompanySearchResult,
  Contact,
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
  V3QuoteVersion,
  QuoteVersionCreatePayload,
} from './types';
import { API_BASE_URL } from './config';

const API_URL = API_BASE_URL;

async function handleResponse<T>(response: Response): Promise<{ data: T }> {
    if (!response.ok) {
      const errorData = (await response
        .json()
        .catch(() => ({}))) as Record<string, unknown>;
      const message =
        (typeof errorData.detail === 'string' && errorData.detail) ||
        (typeof errorData.error === 'string' && errorData.error) ||
        response.statusText ||
        'An error occurred';
      throw new Error(message);
    }
    const data = (await response
      .json()
      .catch(() => undefined)) as T;
    return { data };
}

export const apiClient = {
  get: async <T>(url: string, options: RequestInit = {}): Promise<{ data: T }> => {
    const response = await fetch(`${API_URL}${url}`, options);
    return handleResponse<T>(response);
  },
  post: async <T>(
    url: string,
    payload: unknown,
    options: RequestInit = {},
  ): Promise<{ data: T }> => {
    const response = await fetch(`${API_URL}${url}`, {
      ...options,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers ?? {}),
      },
      body: JSON.stringify(payload),
    });
    return handleResponse<T>(response);
  },
};

async function fetchWrapper<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'An error occurred');
  }
  return response.json() as Promise<T>;
}

export async function login(data: LoginData): Promise<{ token: string }> {
  return fetchWrapper<{ token: string }>(`${API_URL}/api/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function getMe(token: string): Promise<User> {
  return fetchWrapper<User>(`${API_URL}/api/accounts/me/`, {
    headers: { Authorization: `Token ${token}` },
  });
}

export async function getCustomers(token: string): Promise<Customer[]> {
    return fetchWrapper<Customer[]>(`${API_URL}/api/v3/customers/`, {
      headers: { Authorization: `Token ${token}` },
    });
  }

  export async function getCustomer(token: string, id: string): Promise<Customer> {
    return fetchWrapper<Customer>(`${API_URL}/api/v3/customers/${id}/`, {
      headers: { Authorization: `Token ${token}` },
    });
  }

  export async function createCustomer(token: string, data: Partial<Customer>): Promise<Customer> {
    return fetchWrapper<Customer>(`${API_URL}/api/v3/customers/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Token ${token}`,
      },
      body: JSON.stringify(data),
    });
  }

  export async function updateCustomer(token: string, id: string, data: Partial<Customer>): Promise<Customer> {
    return fetchWrapper<Customer>(`${API_URL}/api/v3/customers/${id}/`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Token ${token}`,
        },
        body: JSON.stringify(data),
    });
}


  export async function getQuotes(token: string): Promise<V3QuoteComputeResponse[]> {
    return fetchWrapper<V3QuoteComputeResponse[]>(`${API_URL}/api/v3/quotes/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function getQuote(token: string, id: string): Promise<V3QuoteComputeResponse> {
    return fetchWrapper<V3QuoteComputeResponse>(`${API_URL}/api/v3/quotes/${id}/`, {
        headers: { Authorization: `Token ${token}` },
    });
}


export async function createQuote(token: string, data: V3QuoteComputeRequest): Promise<V3QuoteComputeResponse> {
    return fetchWrapper<V3QuoteComputeResponse>(`${API_URL}/api/v3/quotes/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Token ${token}`,
        },
        body: JSON.stringify(data),
    });
}

export async function getQuoteVersions(token: string, quoteId: string): Promise<V3QuoteVersion[]> {
    return fetchWrapper<V3QuoteVersion[]>(`${API_URL}/api/v3/quotes/${quoteId}/versions/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function createQuoteVersion(
  token: string,
  quoteId: string,
  data: QuoteVersionCreatePayload,
): Promise<V3QuoteVersion> {
    return fetchWrapper<V3QuoteVersion>(`${API_URL}/api/v3/quotes/${quoteId}/versions/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Token ${token}`,
        },
        body: JSON.stringify(data),
    });
}

export async function listStations(token: string): Promise<{ id: number; iata_code: string }[]> {
    return fetchWrapper<{ id: number; iata_code: string }[]>(`${API_URL}/api/stations/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function getRateCards(token: string): Promise<RatecardFile[]> {
    return fetchWrapper<RatecardFile[]>(`${API_URL}/api/ratecards/ratecard-files/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function uploadRateCard(token: string, file: File, name: string, file_type: string): Promise<RatecardFile> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('file_type', file_type);

    const response = await fetch(`${API_URL}/api/ratecards/ratecard-files/`, {
        method: 'POST',
        headers: {
            Authorization: `Token ${token}`,
        },
        body: formData,
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'An error occurred');
    }
    return response.json();
}

/**
 * Sends a quote request to the V3 calculation engine.
 * @param quoteRequest - The V3 compute payload.
 * @param token - The user's authentication token.
 * @returns A Promise that resolves to the V3 compute response.
 */
export async function computeQuote(
  quoteRequest: V3QuoteComputeRequest,
  token: string,
): Promise<V3QuoteComputeResponse> {
  try {
    const response = await fetch(`${API_URL}/api/v3/quotes/compute/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Token ${token}`,
      },
      body: JSON.stringify(quoteRequest),
    });

    if (!response.ok) {
      const errorData = (await response.json().catch(() => ({}))) as Record<string, unknown>;
      const errorMessage =
        (typeof errorData === 'object' && errorData !== null && 'detail' in errorData
          ? String((errorData as Record<string, unknown>).detail)
          : undefined) ||
        (typeof errorData === 'object' && errorData !== null && 'error' in errorData
          ? String((errorData as Record<string, unknown>).error)
          : undefined) ||
        response.statusText;
      console.error('V3 quote compute error:', errorData);
      throw new Error(errorMessage ?? 'Failed to compute quote.');
    }

    return (await response.json()) as V3QuoteComputeResponse;
  } catch (error) {
    console.error('Error computing V3 quote:', error);
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Error computing V3 quote');
  }
}

/**
 * Searches for companies by name.
 * @param query The search term.
 * @returns A list of matching companies.
 */
export async function searchCompanies(query: string, token: string, signal?: AbortSignal): Promise<CompanySearchResult[]> {
  const trimmedQuery = query.trim();
  if (trimmedQuery.length < 2) {
    return [];
  }

  if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
    throw new Error('API base URL is not configured');
  }

  const params = new URLSearchParams({ q: trimmedQuery });

  try {
    const response = await fetch(`${API_URL}/api/v3/parties/search/?${params.toString()}`, {
      headers: {
        'Authorization': `Token ${token}`,
      },
      signal,
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('API Error searching companies:', response.status, errorData);
      throw new Error('Failed to search companies');
    }
    return (await response.json()) as CompanySearchResult[];
  } catch (error) {
    console.error('Error searching companies:', error);
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Error searching companies');
  }
}

/**
 * Fetches contacts for a specific company ID.
 * @param companyId The UUID of the company.
 * @returns A list of contacts.
 */
export async function getCompanyContacts(companyId: string, token: string): Promise<Contact[]> {
  if (!companyId) return []; // Don't fetch if no company ID

  try {
    const response = await fetch(`${API_URL}/api/v3/parties/companies/${companyId}/contacts/`, {
      headers: {
        'Authorization': `Token ${token}`,
      },
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('API Error fetching company contacts:', response.status, errorData);
      throw new Error("Failed to fetch contacts for the company");
    }
    return await response.json() as Contact[];
  } catch (error) {
    console.error('Error fetching company contacts:', error);
    // Return empty array on error to avoid breaking the UI
    return []; 
  }
}

/**
 * Searches for locations (cities/airports).
 * @param query The search term.
 * @returns A list of matching locations.
 */
export async function searchLocations(query: string, token: string): Promise<{ value: string; label: string }[]> {
  if (query.length < 2) return [];

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API base URL is not configured");
  }

  const normalizedBaseUrl = apiBaseUrl.replace(/\/$/, '');

  try {
    const response = await fetch(`${normalizedBaseUrl}/api/v3/locations/search/?q=${query}`, {
      headers: {
        'Authorization': `Token ${token}`,
      },
    });
    if (!response.ok) {
      throw new Error("Failed to search locations");
    }
    // Map backend response to { value: code, label: display_name } for Combobox
    const data = (await response.json()) as { code: string; display_name: string }[];
    return data.map((loc) => ({
      value: loc.code, // Use the 3-letter code as the value
      label: loc.display_name
    }));
  } catch (error) {
    console.error('Error searching locations:', error);
    return []; // Return empty on error
  }
}
