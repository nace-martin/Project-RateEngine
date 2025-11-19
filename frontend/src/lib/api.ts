// frontend/src/lib/api.ts
import axios from 'axios';
import { API_BASE_URL } from './config';
import {
  LoginData,
  User,
  CompanySearchResult,
  Contact,
  AirportSearchResult,
  LocationSearchResult,
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
  RatecardFile,
  Customer,
  QuoteVersionCreatePayload,
  StationSummary,
} from './types';

// Helper to get the token
const getToken = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  return localStorage.getItem('authToken');
};

const resolveAuthToken = (tokenOverride?: string | null): string => {
  const token = tokenOverride ?? getToken();
  if (!token) {
    throw new Error('Authentication token not available. Please log in.');
  }
  return token;
};

const parseErrorResponse = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    if (typeof data === 'string') {
      return data;
    }
    if (data && typeof data === 'object') {
      if ('detail' in data && typeof data.detail === 'string') {
        return data.detail;
      }
      return JSON.stringify(data);
    }
  } catch {
    // ignore parse errors
  }
  return response.statusText || 'Unknown error';
};

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Token ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// --- Auth ---

type RawLoginResponse = {
  token?: string;
  role?: string;
  username?: string;
  id?: number;
  user_id?: number;
  user?: Partial<User>;
};

export async function login(
  data: LoginData,
): Promise<{ token: string; user: User }> {
  const url = API_BASE_URL + '/api/auth/login/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Login failed. Please check your username and password.');
  }

  const rawResult = (await response.json()) as RawLoginResponse | null;
  const result: RawLoginResponse = rawResult ?? {};
  const token = typeof result.token === 'string' ? result.token : null;

  if (!token) {
    throw new Error('Login response did not include an auth token.');
  }

  const rawUser = result.user && typeof result.user === 'object' ? result.user : undefined;
  const idCandidates = [
    rawUser?.id,
    result.id,
    result.user_id,
  ];
  const normalizedUser: User = {
    id: idCandidates.find((value): value is number => typeof value === 'number') ?? 0,
    username:
      (rawUser && typeof rawUser.username === 'string' && rawUser.username) ??
      (typeof result.username === 'string' ? result.username : data.username),
    role:
      (rawUser && typeof rawUser.role === 'string' && rawUser.role) ??
      (typeof result.role === 'string' ? result.role : 'sales'),
  };

  return {
    token,
    user: normalizedUser,
  };
}

export async function getMe(): Promise<User> {
  const url = API_BASE_URL + '/api/accounts/me/';
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch user data.');
  }

  return response.json();
}

// --- Parties (Companies/Contacts) ---

export async function getCompanies(
  query: string,
): Promise<CompanySearchResult[]> {
  const url = API_BASE_URL + `/api/v3/parties/companies/search/?q=${query}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });
  if (!response.ok) {
    throw new Error('Failed to search companies');
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
    throw new Error('Failed to fetch contacts');
  }
  return response.json();
}

// --- Airport Search ---

export async function searchAirports(
  query: string,
): Promise<AirportSearchResult[]> {
  const url =
    API_BASE_URL + `/api/v3/core/airports/search/?search=${encodeURIComponent(query)}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to search airports');
  }

  return response.json();
}

// --- General Location Search ---

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
    throw new Error('Failed to search locations');
  }

  return response.json();
}

// --- Quotes V3 ---

export async function getQuotesV3(): Promise<V3QuoteComputeResponse[]> {
  const url = API_BASE_URL + '/api/v3/quotes/';
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch quotes.');
  }

  return response.json();
}

export async function computeQuoteV3(
  data: V3QuoteComputeRequest,
): Promise<V3QuoteComputeResponse> {
  const url = API_BASE_URL + '/api/v3/quotes/compute/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    let errorData: unknown = null;
    try {
      errorData = await response.json();
    } catch {
      // ignore parse errors so we can still surface a useful message
    }
    console.error('Quote compute error:', errorData || response.statusText);

    let message = response.statusText || 'Unknown error';
    if (typeof errorData === 'string') {
      message = errorData;
    } else if (errorData && typeof errorData === 'object') {
      const payload = errorData as Record<string, unknown>;
      if ('detail' in payload && typeof payload.detail === 'string') {
        message = payload.detail;
      } else if (Object.keys(payload).length > 0) {
        message = JSON.stringify(payload);
      }
    }

    throw new Error(`Failed to create quote: ${message}`);
  }

  return response.json();
}

export async function getQuoteV3(
  quoteId: string,
): Promise<V3QuoteComputeResponse> {
  const url = API_BASE_URL + `/api/v3/quotes/${quoteId}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch quote details.');
  }

  return response.json();
}


// --- Rate Cards ---

export async function uploadRatecard(
  file: File,
  supplierId: string,
  tokenOverride?: string | null,
): Promise<RatecardFile> {
  const url = API_BASE_URL + '/api/v3/ratecards/upload/';
  const formData = new FormData();
  formData.append('file', file);
  formData.append('supplier_id', supplierId);

  const token = resolveAuthToken(tokenOverride);
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Token ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json();
    console.error('Rate card upload error:', errorData);
    throw new Error(
      `Failed to upload rate card: ${errorData.detail || response.statusText}`,
    );
  }

  return response.json();
}

export async function getRateCards(tokenOverride?: string | null): Promise<RatecardFile[]> {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + '/api/v3/ratecards/';
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${token}`,
    },
  });

  if (!response.ok) {
    if (response.status === 404) {
      return [];
    }
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch rate cards: ${detail}`);
  }

  return response.json();
}

export async function getCustomer(tokenOverride: string | null | undefined, customerId: string): Promise<Customer> {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + `/api/v3/customers/${customerId}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${token}`,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch customer: ${detail}`);
  }

  return response.json();
}

export async function updateCustomer(
  tokenOverride: string | null | undefined,
  customerId: string,
  payload: Partial<Customer>,
): Promise<Customer> {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + `/api/v3/customers/${customerId}/`;
  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update customer: ${detail}`);
  }

  return response.json();
}

export async function listStations(tokenOverride?: string | null): Promise<StationSummary[]> {
  const token = resolveAuthToken(tokenOverride);
  const searchFallback = 'a'; // basic seed term to return a reasonable list
  const url = API_BASE_URL + `/api/v3/core/airports/search/?search=${encodeURIComponent(searchFallback)}`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${token}`,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch stations: ${detail}`);
  }

  const airports: AirportSearchResult[] = await response.json();
  return airports.map((airport, index) => ({
    id: index + 1,
    iata_code: airport.iata_code,
    name: airport.name,
    city_country: airport.city_country,
  }));
}

export async function createQuoteVersion(
  tokenOverride: string | null | undefined,
  quoteId: string,
  payload: QuoteVersionCreatePayload,
) {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + `/api/v3/quotes/${quoteId}/versions/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create quote version: ${detail}`);
  }

  return response.json();
}

export async function uploadRateCard(
  tokenOverride: string | null | undefined,
  file: File,
  supplierId: string,
  _fileType?: string,
) {
  void _fileType;
  return uploadRatecard(file, supplierId, tokenOverride);
}
