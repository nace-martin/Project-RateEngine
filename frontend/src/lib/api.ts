import {
  LoginData,
  User,
  Customer,
  Quote,
  QuoteVersion,
  QuoteContext,
  BuyOffer,
  RatecardFile,
  CompanySearchResult,
  QuoteV2Request,
  QuoteV2Response,
} from './types';
import { API_BASE_URL } from './config';

const API_URL = API_BASE_URL;

export const apiClient = {
  get: async <T>(url: string, options: RequestInit = {}): Promise<{ data: T }> => {
    const response = await fetch(`${API_URL}${url}`, options);
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'An error occurred');
    }
    const data = await response.json();
    return { data };
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
  return fetchWrapper<{ token: string }>(`${API_URL}/accounts/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function getMe(token: string): Promise<User> {
  return fetchWrapper<User>(`${API_URL}/accounts/me/`, {
    headers: { Authorization: `Token ${token}` },
  });
}

export async function getCustomers(token: string): Promise<Customer[]> {
    return fetchWrapper<Customer[]>(`${API_URL}/customers/`, {
      headers: { Authorization: `Token ${token}` },
    });
  }

  export async function getCustomer(token: string, id: string): Promise<Customer> {
    return fetchWrapper<Customer>(`${API_URL}/customers/${id}/`, {
      headers: { Authorization: `Token ${token}` },
    });
  }

  export async function createCustomer(token: string, data: Partial<Customer>): Promise<Customer> {
    return fetchWrapper<Customer>(`${API_URL}/customers/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Token ${token}`,
      },
      body: JSON.stringify(data),
    });
  }

  export async function updateCustomer(token: string, id: string, data: Partial<Customer>): Promise<Customer> {
    return fetchWrapper<Customer>(`${API_URL}/customers/${id}/`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Token ${token}`,
        },
        body: JSON.stringify(data),
    });
}


  export async function getQuotes(token: string): Promise<Quote[]> {
    return fetchWrapper<Quote[]>(`${API_URL}/quotes/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function getQuote(token: string, id: string): Promise<Quote> {
    return fetchWrapper<Quote>(`${API_URL}/quotes/${id}/`, {
        headers: { Authorization: `Token ${token}` },
    });
}


export async function createQuote(token: string, data: Partial<Quote>): Promise<Quote> {
    return fetchWrapper<Quote>(`${API_URL}/quotes/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Token ${token}`,
        },
        body: JSON.stringify(data),
    });
}

export async function getQuoteVersions(token: string, quoteId: string): Promise<QuoteVersion[]> {
    return fetchWrapper<QuoteVersion[]>(`${API_URL}/quotes/${quoteId}/versions/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function createQuoteVersion(token: string, quoteId: string, data: Partial<QuoteVersion>): Promise<QuoteVersion> {
    return fetchWrapper<QuoteVersion>(`${API_URL}/quotes/${quoteId}/versions/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Token ${token}`,
        },
        body: JSON.stringify(data),
    });
}

export async function listStations(token: string): Promise<{ id: number; iata_code: string }[]> {
    return fetchWrapper<{ id: number; iata_code: string }[]>(`${API_URL}/stations/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function getRateCards(token: string): Promise<RatecardFile[]> {
    return fetchWrapper<RatecardFile[]>(`${API_URL}/ratecards/ratecard-files/`, {
        headers: { Authorization: `Token ${token}` },
    });
}

export async function uploadRateCard(token: string, file: File, name: string, file_type: string): Promise<RatecardFile> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', name);
    formData.append('file_type', file_type);

    const response = await fetch(`${API_URL}/ratecards/ratecard-files/`, {
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
 * Sends a quote request to the v2 calculation engine.
 * @param quoteDetails - The context for the quote, including origin, destination, and pieces.
 * @param token - The user's authentication token.
 * @returns A Promise that resolves to the calculated BuyOffer.
 */
export async function calculateQuoteV2(quoteDetails: QuoteContext, token: string): Promise<BuyOffer> {
  const response = await fetch(`${API_URL}/quotes/compute/v2/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Token ${token}`,
    },
    body: JSON.stringify(quoteDetails),
  });

  if (!response.ok) {
    const errorData = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    const errorMessage =
      (typeof errorData.error === 'string' && errorData.error) ||
      `An error occurred: ${response.statusText}`;
    throw new Error(errorMessage);
  }

  return response.json();
}

/**
 * Creates a new quote using the V2 pricing engine.
 * @param quoteRequest The data for the new quote.
 * @returns The newly created quote object from the backend.
 */
export async function createQuoteV2(quoteRequest: QuoteV2Request): Promise<QuoteV2Response> {
  try {
    const response = await fetch(`${API_URL}/v2/quotes/compute/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        // If you have authentication, the token would go here
        // 'Authorization': `Bearer ${token}`,
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
        JSON.stringify(errorData);
      console.error('API Error:', errorData);
      throw new Error(`Failed to create quote: ${errorMessage}`);
    }

    return (await response.json()) as QuoteV2Response;
  } catch (error) {
    console.error('Error creating V2 quote:', error);
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Error creating V2 quote');
  }
}

/**
 * Searches for companies by name.
 * @param query The search term.
 * @returns A list of matching companies.
 */
export async function searchCompanies(query: string, signal?: AbortSignal): Promise<CompanySearchResult[]> {
  const trimmedQuery = query.trim();
  if (trimmedQuery.length < 2) {
    return [];
  }

  if (!process.env.NEXT_PUBLIC_API_BASE_URL) {
    throw new Error('API base URL is not configured');
  }

  const params = new URLSearchParams({ q: trimmedQuery });

  try {
    const response = await fetch(`${API_URL}/v2/parties/search/?${params.toString()}`, { signal });
    if (!response.ok) {
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
 * Fetches a single quote by its ID from the V2 endpoint.
 * @param quoteId The ID of the quote to fetch.
 * @returns The quote object.
 */
export async function getQuoteV2(quoteId: string): Promise<QuoteV2Response> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API base URL is not configured");
  }

  try {
    const response = await fetch(`${apiBaseUrl}/v2/quotes/${quoteId}/`, {
      headers: {
        'Content-Type': 'application/json',
        // Add Authorization header if needed
      },
    });

    if (!response.ok) {
      const errorData = (await response.json()) as Record<string, unknown>;
      console.error('API Error fetching quote:', errorData);
      throw new Error(`Failed to fetch quote: ${response.statusText}`);
    }

    return (await response.json()) as QuoteV2Response;
  } catch (error) {
    console.error('Error fetching V2 quote:', error);
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('Error fetching V2 quote');
  }
}

/**
 * Fetches contacts for a specific company ID.
 * @param companyId The UUID of the company.
 * @returns A list of contacts.
 */
export async function getCompanyContacts(companyId: string): Promise<{ id: string; first_name: string; last_name: string; email: string }[]> {
  if (!companyId) return []; // Don't fetch if no company ID

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API base URL is not configured");
  }

  try {
    const response = await fetch(`${apiBaseUrl}/v2/parties/companies/${companyId}/contacts/`);
    if (!response.ok) {
      // Handle 404 specifically if needed, otherwise generic error
      throw new Error("Failed to fetch contacts for the company");
    }
    return await response.json();
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
export async function searchLocations(query: string): Promise<{ value: string; label: string }[]> {
  if (query.length < 2) return [];

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("API base URL is not configured");
  }

  try {
    const response = await fetch(`${apiBaseUrl}/v2/locations/search/?q=${query}`);
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
