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
  Customer,
  QuoteVersionCreatePayload,
  StationSummary,
  QuoteComputeResult,
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
      ((rawUser && typeof rawUser.username === 'string') ? rawUser.username : undefined) ??
      (typeof result.username === 'string' ? result.username : data.username),
    role:
      ((rawUser && typeof rawUser.role === 'string') ? rawUser.role : undefined) ??
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

export async function getQuoteCompute(
  quoteId: string,
): Promise<QuoteComputeResult> {
  const url = API_BASE_URL + `/api/v3/quotes/${quoteId}/compute_v3/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch quote computation: ${detail}`);
  }

  return response.json();
}


// --- Rate Cards ---





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



// --- Pricing V3 Zones ---
export interface Zone {
  id: string;
  code: string;
  name: string;
  mode: string;
  partner?: string;
  members: { id: string; location_name: string; location_code: string }[];
}

export async function getZones(): Promise<Zone[]> {
  const url = API_BASE_URL + '/api/v3/zones/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch zones');
  return response.json();
}

export async function createZone(data: Partial<Zone>): Promise<Zone> {
  const url = API_BASE_URL + '/api/v3/zones/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to create zone');
  return response.json();
}

// --- Pricing V3 Rate Cards ---
export interface RateBreak {
  id: string;
  from_value: number;
  to_value: number | null;
  rate: number;
}

export interface RateLine {
  id: string;
  component: string;
  component_code?: string;
  method: string;
  unit: string | null;
  min_charge: number;
  percent_value: number | null;
  percent_of_component: string | null;
  description: string;
  breaks: RateBreak[];
}

export interface RateCard {
  id: string;
  name: string;
  supplier: string;
  supplier_name?: string;
  mode: string;
  origin_zone: string;
  origin_zone_name?: string;
  destination_zone: string;
  destination_zone_name?: string;
  currency: string;
  scope: string;
  valid_from: string;
  valid_until: string | null;
  priority: number;
  lines?: RateLine[];
}

export async function getRateCardsV3(): Promise<RateCard[]> {
  const url = API_BASE_URL + '/api/v3/rate-cards/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch rate cards');
  return response.json();
}

export async function createRateCardV3(data: Partial<RateCard>): Promise<RateCard> {
  const url = API_BASE_URL + '/api/v3/rate-cards/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create rate card: ${detail}`);
  }
  return response.json();
}

export async function importRateCardCSV(id: string, file: File): Promise<{ message: string; errors: string[] }> {
  const url = API_BASE_URL + `/api/v3/rate-cards/${id}/import_csv/`;
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: formData,
  });

  if (!response.ok && response.status !== 207) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to import CSV: ${detail}`);
  }
  return response.json();
}

// --- Spot Rates ---

export interface SpotCharge {
  id?: string;
  spot_rate: string;
  component: string;
  component_code?: string;
  component_description?: string;
  method: string;
  unit?: string;
  rate: string;
  min_charge: string;
  percent_value?: string;
  percent_of_component?: string;
  description: string;
}

export interface SpotRate {
  id: string;
  quote: string;
  supplier: string;
  supplier_name?: string;
  origin_location: string;
  origin_location_name?: string;
  destination_location: string;
  destination_location_name?: string;
  mode: string;
  currency: string;
  valid_until?: string;
  notes: string;
  created_at?: string;
  charges: SpotCharge[];
}

export async function getSpotRates(quoteId: string): Promise<SpotRate[]> {
  const url = API_BASE_URL + `/api/v3/spot-rates/?quote=${quoteId}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` }
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch spot rates: ${detail}`);
  }
  return response.json();
}

export async function createSpotRate(data: Partial<SpotRate>): Promise<SpotRate> {
  const url = API_BASE_URL + '/api/v3/spot-rates/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create spot rate: ${detail}`);
  }
  return response.json();
}

export async function updateSpotRate(id: string, data: Partial<SpotRate>): Promise<SpotRate> {
  const url = API_BASE_URL + `/api/v3/spot-rates/${id}/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update spot rate: ${detail}`);
  }
  return response.json();
}

export async function deleteSpotRate(id: string): Promise<void> {
  const url = API_BASE_URL + `/api/v3/spot-rates/${id}/`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Token ${resolveAuthToken()}` }
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to delete spot rate: ${detail}`);
  }
}

export async function createSpotCharge(data: Partial<SpotCharge>): Promise<SpotCharge> {
  const url = API_BASE_URL + '/api/v3/spot-charges/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create spot charge: ${detail}`);
  }
  return response.json();
}

export async function updateSpotCharge(id: string, data: Partial<SpotCharge>): Promise<SpotCharge> {
  const url = API_BASE_URL + `/api/v3/spot-charges/${id}/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update spot charge: ${detail}`);
  }
  return response.json();
}

export async function deleteSpotCharge(id: string): Promise<void> {
  const url = API_BASE_URL + `/api/v3/spot-charges/${id}/`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Token ${resolveAuthToken()}` }
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to delete spot charge: ${detail}`);
  }
}

export async function getRateCardV3(id: string): Promise<RateCard> {
  const url = API_BASE_URL + `/api/v3/rate-cards/${id}/`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch rate card details');
  return response.json();
}

export async function createRateLine(data: Partial<RateLine>): Promise<RateLine> {
  const url = API_BASE_URL + '/api/v3/rate-lines/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create rate line: ${detail}`);
  }
  return response.json();
}

export async function updateRateLine(id: string, data: Partial<RateLine>): Promise<RateLine> {
  const url = API_BASE_URL + `/api/v3/rate-lines/${id}/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update rate line: ${detail}`);
  }
  return response.json();
}

// --- Services ---
export interface ServiceComponent {
  id: string;
  code: string;
  description: string;
  mode: string;
  category: string;
}

export async function getServiceComponents(): Promise<ServiceComponent[]> {
  const url = API_BASE_URL + '/api/v3/services/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch service components');
  return response.json();
}
