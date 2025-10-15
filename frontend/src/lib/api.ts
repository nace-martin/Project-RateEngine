import { LoginData, User, Customer, Quote, QuoteVersion, QuoteContext, BuyOffer } from './types';
import { RatecardFile } from './types';

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api').replace(/\/$/, '');
const API_URL = API_BASE;

async function fetchWrapper<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.detail || 'An error occurred');
  }
  return response.json();
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
    // Try to parse the error response from the backend
    const errorData = await response.json().catch(() => ({})); // Provide a fallback empty object
    const errorMessage = errorData.error || `An error occurred: ${response.statusText}`;
    throw new Error(errorMessage);
  }

  return response.json();
}
