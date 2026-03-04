// frontend/src/lib/api.ts
import axios from 'axios';
import { API_BASE_URL } from './config';
import { ReplyAnalysisResult, SPEChargeLine, SPEConditions, SPECommodity } from './spot-types';
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
  PaginatedResponse,
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

export async function getQuotesV3(params?: {
  mode?: string;
  status?: string;
  created_by?: string;
  is_archived?: boolean;
}): Promise<PaginatedResponse<V3QuoteComputeResponse>> {
  const url = new URL(API_BASE_URL + '/api/v3/quotes/');
  if (params) {
    if (params.mode) url.searchParams.append('mode', params.mode);
    if (params.status) url.searchParams.append('status', params.status);
    if (params.created_by) url.searchParams.append('created_by', params.created_by);
    if (params.is_archived !== undefined) url.searchParams.append('is_archived', String(params.is_archived));
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: 'no-store', // Ensure we always get fresh data
  });

  if (!response.ok) {
    throw new Error('Failed to fetch quotes.');
  }

  const data = await response.json();
  if (Array.isArray(data)) {
    return {
      count: data.length,
      next: null,
      previous: null,
      results: data,
    };
  }
  if (data && typeof data === 'object' && Array.isArray(data.results)) {
    return data as PaginatedResponse<V3QuoteComputeResponse>;
  }
  throw new Error('Unexpected quotes response format.');
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

function mapQuoteDetailToComputeResult(quote: V3QuoteComputeResponse): QuoteComputeResult {
  const version = quote.latest_version;
  const totals = version?.totals;
  const lines = version?.lines ?? [];
  const displayCurrency = totals?.currency || totals?.total_sell_fcy_currency || quote.output_currency || 'PGK';

  const exchange_rates: Record<string, string> = {};
  for (const line of lines) {
    const rate = line.exchange_rate;
    const ccy = (line.cost_fcy_currency || line.sell_fcy_currency || '').toUpperCase();
    if (!rate || !ccy || ccy === 'PGK') continue;
    exchange_rates[`${ccy}/PGK`] = rate;
  }

  return {
    quote_id: quote.id,
    quote_number: quote.quote_number,
    buy_lines: [],
    sell_lines: lines.map((line) => {
      const sellCurrency = line.sell_fcy_currency || displayCurrency;
      const lineGstAmount =
        (sellCurrency || '').toUpperCase() !== 'PGK'
          ? (parseFloat(line.sell_fcy_incl_gst || '0') - parseFloat(line.sell_fcy || '0'))
          : (parseFloat(line.sell_pgk_incl_gst || '0') - parseFloat(line.sell_pgk || '0'));
      return {
        line_type: 'COMPONENT',
        component: line.service_component?.code ?? null,
        description: line.cost_source_description || line.service_component?.description || 'Charge',
        leg: line.service_component?.leg || undefined,
        cost_pgk: line.cost_pgk,
        sell_pgk: line.sell_pgk,
        sell_pgk_incl_gst: line.sell_pgk_incl_gst,
        gst_amount: lineGstAmount.toFixed(2),
        sell_fcy: line.sell_fcy,
        sell_fcy_incl_gst: line.sell_fcy_incl_gst,
        sell_currency: sellCurrency,
        margin_percent: '0',
        exchange_rate: line.exchange_rate || '0',
        source: line.cost_source || 'stored_quote',
        is_informational: false,
      };
    }),
    totals: {
      total_sell_ex_gst:
        displayCurrency.toUpperCase() !== 'PGK'
          ? (totals?.total_sell_fcy || totals?.total_sell_pgk || '0')
          : (totals?.total_sell_pgk || '0'),
      cost_pgk: totals?.total_cost_pgk || '0',
      sell_pgk: totals?.total_sell_pgk || '0',
      sell_pgk_incl_gst: totals?.total_sell_pgk_incl_gst || totals?.total_sell_pgk || '0',
      gst_amount: (
        displayCurrency.toUpperCase() !== 'PGK'
          ? (
            (parseFloat(totals?.total_sell_fcy_incl_gst || totals?.total_sell_fcy || '0')) -
            (parseFloat(totals?.total_sell_fcy || '0'))
          )
          : (
            (parseFloat(totals?.total_sell_pgk_incl_gst || totals?.total_sell_pgk || '0')) -
            (parseFloat(totals?.total_sell_pgk || '0'))
          )
      ).toFixed(2),
      caf_pgk: '0',
      currency: displayCurrency,
      total_sell_fcy: totals?.total_sell_fcy || totals?.total_sell_pgk || '0',
      total_sell_fcy_incl_gst: totals?.total_sell_fcy_incl_gst || totals?.total_sell_pgk_incl_gst || '0',
      total_quote_amount:
        displayCurrency.toUpperCase() !== 'PGK'
          ? (totals?.total_sell_fcy_incl_gst || totals?.total_sell_fcy || '0')
          : (totals?.total_sell_pgk_incl_gst || totals?.total_sell_pgk || '0'),
      total_sell_fcy_currency: totals?.total_sell_fcy_currency || displayCurrency,
    },
    exchange_rates,
    computation_date: version?.created_at || quote.updated_at || quote.created_at,
    notes: totals?.notes ? [totals.notes] : [],
  };
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

  if (response.status === 404) {
    const quote = await getQuoteV3(quoteId);
    return mapQuoteDetailToComputeResult(quote);
  }

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
  const url = API_BASE_URL + '/api/v3/ratecards/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch rate cards: ${detail}`);
  }
  return response.json();
}

export async function createRateCardV3(data: Partial<RateCard>): Promise<RateCard> {
  const url = API_BASE_URL + '/api/v3/ratecards/';
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
  // Deprecated V3 helper kept for compatibility with legacy dialogs.
  // Internally routes to the V4 bulk uploader endpoint.
  void id;
  try {
    const result = await uploadV4RateCardCSV(file);
    return { message: result.message, errors: [] };
  } catch (error) {
    if (error instanceof V4RateCardUploadValidationError) {
      return {
        message: error.message,
        errors: Object.entries(error.errors).map(([rowKey, reason]) => `${rowKey}: ${reason}`),
      };
    }
    throw error;
  }
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
  const url = API_BASE_URL + `/api/v3/ratecards/${id}/`;
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

// --- Quote Clone ---

export interface CloneQuoteResponse {
  id: string;
  quote_number: string;
  status: string;
  cloned_from: {
    id: string;
    quote_number: string;
  };
  spot_charges_copied: number;
  created_at: string;
}

export async function cloneQuote(quoteId: string): Promise<CloneQuoteResponse> {
  const url = API_BASE_URL + `/api/v3/quotes/${quoteId}/clone/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to clone quote');
  }

  return response.json();
}

// --- Quote Status Transitions ---

export async function transitionQuoteStatus(
  quoteId: string,
  action: "finalize" | "send" | "cancel" | "mark_won" | "mark_lost" | "mark_expired"
): Promise<{ success: boolean; error?: string }> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v3/quotes/${quoteId}/transition/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Token ${resolveAuthToken()}`
      },
      body: JSON.stringify({ action }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return { success: false, error: data.detail || "Failed to update status" };
    }

    return { success: true };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : "Network error" };
  }
}

// --- Quote PDF Export ---

type QuotePDFOptions = {
  summaryOnly?: boolean;
};

/**
 * Download a quote as PDF.
 * Fetches the PDF from the backend and triggers a browser download.
 */
export async function downloadQuotePDF(
  quoteId: string,
  quoteNumber?: string,
  options?: QuotePDFOptions,
): Promise<void> {
  const params = new URLSearchParams();
  if (options?.summaryOnly) {
    params.set('summary', '1');
  }
  const query = params.toString();
  const url = API_BASE_URL + `/api/v3/quotes/${quoteId}/pdf/` + (query ? `?${query}` : '');
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Authorization: `Token ${resolveAuthToken()}`
    },
  });

  if (!response.ok) {
    // Try to get error details from JSON response
    let errorMessage = `HTTP ${response.status}: `;
    try {
      const data = await response.json();
      errorMessage += data.detail || data.message || JSON.stringify(data);
    } catch {
      errorMessage += response.statusText || 'Failed to download PDF';
    }
    throw new Error(errorMessage);
  }

  // Get the blob from response
  const blob = await response.blob();

  // Create download link
  const downloadUrl = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = downloadUrl;
  const suffix = options?.summaryOnly ? '-summary' : '';
  link.download = quoteNumber ? `${quoteNumber}${suffix}.pdf` : `quote${suffix}.pdf`;

  // Trigger download
  document.body.appendChild(link);
  link.click();

  // Cleanup
  document.body.removeChild(link);
  window.URL.revokeObjectURL(downloadUrl);
}

// =============================================================================
// SPOT MODE APIs
// =============================================================================

import type {
  ScopeValidateRequest,
  ScopeValidateResponse,
  TriggerEvaluateRequest,
  TriggerEvaluateResponse,
  CreateSPERequest,
  SpotPricingEnvelope,
  SPEComputeRequest,
  SPEComputeResponse,
} from './spot-types';

/**
 * Validate shipment is within PNG scope.
 * Must be called BEFORE any SPOT logic.
 */
export async function validateSpotScope(
  request: ScopeValidateRequest
): Promise<ScopeValidateResponse> {
  const url = API_BASE_URL + '/api/v3/spot/validate-scope/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Scope validation failed: ${detail}`);
  }

  return response.json();
}

/**
 * Evaluate if SPOT mode is required for shipment.
 */
export async function evaluateSpotTrigger(
  request: TriggerEvaluateRequest
): Promise<TriggerEvaluateResponse> {
  const url = API_BASE_URL + '/api/v3/spot/evaluate-trigger/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Trigger evaluation failed: ${detail}`);
  }

  return response.json();
}

/**
 * Create a new SPOT Pricing Envelope.
 */
export async function createSpotEnvelope(
  request: CreateSPERequest
): Promise<SpotPricingEnvelope> {
  const url = API_BASE_URL + '/api/v3/spot/envelopes/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create SPE: ${detail}`);
  }

  return response.json();
}

/**
 * Update a DRAFT SPOT Pricing Envelope.
 */
export async function updateSpotEnvelope(
  id: string,
  data: { charges?: Omit<SPEChargeLine, 'id'>[]; conditions?: Partial<SPEConditions> }
): Promise<SpotPricingEnvelope> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update SPE: ${detail}`);
  }

  return response.json();
}

/**
 * Get SPOT Pricing Envelope by ID.
 */
export async function getSpotEnvelope(id: string): Promise<SpotPricingEnvelope> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to get SPE: ${detail}`);
  }

  return response.json();
}

/**
 * Submit Sales acknowledgement for SPE.
 */
export async function acknowledgeSpotEnvelope(
  id: string
): Promise<{ success: boolean; status: string }> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/acknowledge/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Acknowledgement failed: ${detail}`);
  }

  return response.json();
}

/**
 * Submit Manager approval for SPE.
 */
export async function approveSpotEnvelope(
  id: string,
  approved: boolean,
  comment?: string
): Promise<{ success: boolean; status: string; approved: boolean }> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/approve/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify({ approved, comment }),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Approval failed: ${detail}`);
  }

  return response.json();
}

/**
 * Compute SPOT quote using SPE charges.
 */
export async function computeSpotQuote(
  id: string,
  request: SPEComputeRequest
): Promise<SPEComputeResponse> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/compute/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  // Allow 400 responses with validation errors
  const data = await response.json();

  if (!response.ok && response.status !== 400) {
    throw new Error(data.error || 'SPOT quote computation failed');
  }

  return data;
}

/**
 * Analyze agent rate reply text and return assertions.
 */
export async function analyzeSpotReply(
  text: string,
  assertions: import('./spot-types').ExtractedAssertion[] = [],
  speId?: string,
  useAi: boolean = true
): Promise<ReplyAnalysisResult> {
  const url = API_BASE_URL + '/api/v3/spot/analyze-reply/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify({
      text,
      assertions,
      spe_id: speId,
      use_ai: useAi
    }),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Reply analysis failed: ${detail}`);
  }

  return response.json();
}

export async function getSpotStandardCharges(request: {
  origin_code: string;
  destination_code: string;
  direction: 'EXPORT' | 'IMPORT' | 'DOMESTIC';
  service_scope: string;
  weight_kg: number;
  commodity: SPECommodity;
}): Promise<SPEChargeLine[]> {
  const url = API_BASE_URL + '/api/v3/spot/standard-charges/';
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch standard SPOT charges: ${detail}`);
  }
  const data = await response.json();
  return Array.isArray(data?.charges) ? data.charges : [];
}


export async function createSpotQuote(
  speId: string,
  request: {
    payment_term: string;
    service_scope: string;
    output_currency: string;
    customer_id?: string;
  }
): Promise<{ success: boolean; quote_id: string; quote_number: string }> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${speId}/create-quote/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`
    },
    body: JSON.stringify({ quote_request: request }),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create quote: ${detail}`);
  }
  return response.json();
}

/**
 * List user's SPOT Pricing Envelopes.
 * Optionally filter by status (e.g., 'draft' for in-progress quotes).
 */
export async function listSpotEnvelopes(
  status?: 'draft' | 'ready' | 'expired' | 'rejected'
): Promise<SpotPricingEnvelope[]> {
  let url = API_BASE_URL + '/api/v3/spot/envelopes/';
  if (status) {
    url += `?status=${status}`;
  }
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to list SPEs: ${detail}`);
  }

  return response.json();
}

// --- Reporting ---

export interface DashboardReportData {
  total_revenue: number;
  volume_by_mode: Array<{ mode: string; count: number; revenue: number }>;
  conversion: {
    total: number;
    drafts: number;
    finalized: number;
    lost: number;
  };
}

export async function getDashboardReports(): Promise<DashboardReportData> {
  const url = API_BASE_URL + '/api/v3/reports/dashboard/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch dashboard reports');
  return response.json();
}

// --- Dashboard Metrics with Timeframe Support ---

export type DashboardTimeframe = 'weekly' | 'monthly' | 'ytd';

export interface DashboardMetricsData {
  timeframe: DashboardTimeframe;
  start_date: string;
  end_date: string;

  // Pipeline metrics
  pipeline_count: number;
  pipeline_value: number;

  // Finalized metrics
  finalized_count: number;
  finalized_value: number;

  // Sales efficiency metrics
  total_quotes_sent: number;
  quotes_accepted: number;
  quotes_lost: number;
  quotes_expired: number;
  win_rate_percent: number;
  avg_quote_value: number;
  lost_opportunity_value: number;

  // Chart data
  weekly_activity: Array<{ day: string; count: number }>;
}

export async function getDashboardMetrics(
  timeframe: DashboardTimeframe = 'monthly'
): Promise<DashboardMetricsData> {
  const url = API_BASE_URL + `/api/v3/reports/dashboard_metrics/?timeframe=${timeframe}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch dashboard metrics');
  return response.json();
}

export interface SalesPerformanceData {
  created_by__username: string;
  created_by__first_name: string;
  created_by__last_name: string;
  total_quotes: number;
  total_revenue: number | null;
  converted_quotes: number;
}

export async function getSalesPerformanceReports(): Promise<SalesPerformanceData[]> {
  const url = API_BASE_URL + '/api/v3/reports/sales_performance/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch sales performance');
  return response.json();
}

// --- Commercial Reporting (Phase 1 MVP) ---

export interface ReportFilters {
  start_date?: string;
  end_date?: string;
  user_id?: string;
  mode?: 'AIR' | 'SEA' | '';
}

export interface FunnelMetricsData {
  quotes_created: number;
  quotes_sent: number;
  quotes_accepted: number;
  quotes_lost: number;
  conversion_rate: number;
  avg_time_to_quote_minutes: number | null;
  filters: ReportFilters;
}

export interface ModeBreakdown {
  mode: string;
  revenue: number;
  cost: number;
  gross_profit: number;
  margin_percent: number;
  count: number;
}

export interface RevenueMarginData {
  total_revenue: number;
  total_cost: number;
  total_gross_profit: number;
  avg_margin_percent: number;
  by_mode: ModeBreakdown[];
  filters: ReportFilters;
}

export interface UserPerformanceItem {
  user_id: number;
  username: string;
  full_name: string;
  quotes_issued: number;
  quotes_sent: number;
  quotes_won: number;
  quotes_lost: number;
  conversion_rate: number;
  total_revenue: number;
  total_gp: number;
  avg_margin: number;
}

export interface UserPerformanceData {
  users: UserPerformanceItem[];
  filters: ReportFilters;
}

function buildReportQueryParams(filters: ReportFilters): string {
  const params = new URLSearchParams();
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  if (filters.user_id) params.append('user_id', filters.user_id);
  if (filters.mode) params.append('mode', filters.mode);
  return params.toString();
}

export async function getFunnelMetrics(filters: ReportFilters = {}): Promise<FunnelMetricsData> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/funnel_metrics/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch funnel metrics');
  return response.json();
}

export async function getRevenueMargin(filters: ReportFilters = {}): Promise<RevenueMarginData> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/revenue_margin/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch revenue margin');
  return response.json();
}

export async function getUserPerformance(filters: ReportFilters = {}): Promise<UserPerformanceData> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/user_performance/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch user performance');
  return response.json();
}

export async function exportReportData(filters: ReportFilters = {}): Promise<Blob> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/export_data/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to export report data');
  return response.blob();
}

export async function getTier1Stats(start_date?: string, end_date?: string): Promise<import('./types').Tier1Stats> {
  const params = new URLSearchParams();
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);

  const url = API_BASE_URL + `/api/v3/reports/tier1_customer_stats/${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch Tier-1 stats');
  }
  return response.json();
}

// =============================================================================
// Customer Discounts API
// =============================================================================

export type DiscountType = 'PERCENTAGE' | 'FLAT_AMOUNT' | 'RATE_REDUCTION' | 'FIXED_CHARGE' | 'MARGIN_OVERRIDE';

export interface CustomerDiscount {
  id: string;
  customer: string;
  customer_name: string;
  product_code: string;
  product_code_code?: string;
  product_code_description?: string;
  product_code_domain?: string;
  product_code_display?: string;
  discount_type: DiscountType;
  discount_type_display?: string;
  discount_value: string;
  currency: string;
  min_charge?: string | null;
  max_charge?: string | null;
  valid_from: string | null;
  valid_until: string | null;
  is_active?: boolean;
  notes: string | null;
  created_at: string;
  created_by?: string | null;
}

export interface ProductCodeOption {
  id: number | string;
  code: string;
  description: string;
  domain: string;
  category: string;
  default_unit?: string;
}

export async function getCustomerDiscounts(params?: {
  customer?: string;
  product_code?: string;
  discount_type?: DiscountType;
  search?: string;
}): Promise<CustomerDiscount[]> {
  const url = new URL(API_BASE_URL + '/api/v4/discounts/');
  if (params) {
    if (params.customer) url.searchParams.append('customer', params.customer);
    if (params.product_code) url.searchParams.append('product_code', params.product_code);
    if (params.discount_type) url.searchParams.append('discount_type', params.discount_type);
    if (params.search) url.searchParams.append('search', params.search);
  }
  const response = await fetch(url.toString(), {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch customer discounts');
  return response.json();
}

export async function getCustomerDiscount(id: string): Promise<CustomerDiscount> {
  const url = API_BASE_URL + `/api/v4/discounts/${id}/`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch discount details');
  return response.json();
}

export async function createCustomerDiscount(data: Partial<CustomerDiscount>): Promise<CustomerDiscount> {
  const url = API_BASE_URL + '/api/v4/discounts/';
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
    throw new Error(`Failed to create discount: ${detail}`);
  }
  return response.json();
}

export async function updateCustomerDiscount(id: string, data: Partial<CustomerDiscount>): Promise<CustomerDiscount> {
  const url = API_BASE_URL + `/api/v4/discounts/${id}/`;
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
    throw new Error(`Failed to update discount: ${detail}`);
  }
  return response.json();
}

export async function deleteCustomerDiscount(id: string): Promise<void> {
  const url = API_BASE_URL + `/api/v4/discounts/${id}/`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to delete discount: ${detail}`);
  }
}

export async function getProductCodes(params?: {
  domain?: string;
  search?: string;
}): Promise<ProductCodeOption[]> {
  const url = new URL(API_BASE_URL + '/api/v4/product-codes/');
  if (params) {
    if (params.domain) url.searchParams.append('domain', params.domain);
    if (params.search) url.searchParams.append('search', params.search);
  }
  const response = await fetch(url.toString(), {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch product codes');
  return response.json();
}


// =============================================================================
// V4 SELL RATES API
// =============================================================================

export interface V4SellRate {
  id: number;
  product_code: number;
  product_code_code: string;
  product_code_description: string;
  origin_airport?: string;
  destination_airport?: string;
  origin_zone?: string;
  destination_zone?: string;
  currency: string;
  rate_per_kg: string | null;
  rate_per_shipment: string | null;
  min_charge: string | null;
  max_charge: string | null;
  percent_rate: string | null;
  weight_breaks: { min_kg: number; rate: string }[] | null;
  is_additive: boolean;
  valid_from: string;
  valid_until: string;
  created_at: string;
  updated_at: string;
}

export async function getExportSellRates(params?: {
  origin?: string;
  destination?: string;
}): Promise<V4SellRate[]> {
  const url = new URL(API_BASE_URL + '/api/v4/rates/export/');
  if (params?.origin) url.searchParams.append('origin_airport', params.origin);
  if (params?.destination) url.searchParams.append('destination_airport', params.destination);
  const response = await fetch(url.toString(), {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch export sell rates');
  return response.json();
}

export async function getImportSellRates(params?: {
  origin?: string;
  destination?: string;
}): Promise<V4SellRate[]> {
  const url = new URL(API_BASE_URL + '/api/v4/rates/import/');
  if (params?.origin) url.searchParams.append('origin_airport', params.origin);
  if (params?.destination) url.searchParams.append('destination_airport', params.destination);
  const response = await fetch(url.toString(), {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch import sell rates');
  return response.json();
}

export async function getDomesticSellRates(params?: {
  origin?: string;
  destination?: string;
}): Promise<V4SellRate[]> {
  const url = new URL(API_BASE_URL + '/api/v4/rates/domestic/');
  if (params?.origin) url.searchParams.append('origin_zone', params.origin);
  if (params?.destination) url.searchParams.append('destination_zone', params.destination);
  const response = await fetch(url.toString(), {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch domestic sell rates');
  return response.json();
}


// =============================================================================
// LOGICAL RATE CARDS API
// =============================================================================

export interface LogicalRateCard {
  id: string;
  name: string;
  description: string;
  service_scope: string | null;
  domain: string;
  lines: V4SellRate[];
  line_count: number;
  currencies: string[];
  corridors: string[];
}

export interface V4RateCardUploadSuccessResponse {
  success: true;
  message: string;
  processed_rows: number;
  created_rows: number;
  updated_rows: number;
}

export interface V4RateCardUploadErrorResponse {
  success?: false;
  message?: string;
  errors?: Record<string, string>;
}

export class V4RateCardUploadValidationError extends Error {
  readonly status: number;
  readonly errors: Record<string, string>;

  constructor(message: string, errors: Record<string, string>, status = 400) {
    super(message);
    this.name = 'V4RateCardUploadValidationError';
    this.status = status;
    this.errors = errors;
  }
}

export async function uploadV4RateCardCSV(file: File): Promise<V4RateCardUploadSuccessResponse> {
  const url = API_BASE_URL + '/api/v4/rates/upload/';
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: formData,
  });

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (response.ok) {
    return payload as V4RateCardUploadSuccessResponse;
  }

  if (response.status === 400 && payload && typeof payload === 'object') {
    const data = payload as V4RateCardUploadErrorResponse;
    throw new V4RateCardUploadValidationError(
      data.message || 'CSV validation failed.',
      data.errors && typeof data.errors === 'object' ? data.errors : {},
      response.status,
    );
  }

  const detail = payload && typeof payload === 'object'
    ? ('message' in (payload as Record<string, unknown>) && typeof (payload as Record<string, unknown>).message === 'string'
      ? String((payload as Record<string, unknown>).message)
      : JSON.stringify(payload))
    : (response.statusText || 'Unknown error');

  throw new Error(`Failed to upload V4 rate card CSV: ${detail}`);
}

export async function getLogicalRateCards(): Promise<LogicalRateCard[]> {
  const url = API_BASE_URL + '/api/v4/rate-cards/';
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch rate cards');
  return response.json();
}

export async function deleteQuoteV3(id: string): Promise<void> {
  const url = API_BASE_URL + `/api/v3/quotes/${id}/`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to delete quote: ${detail}`);
  }
}

export async function deleteSpotEnvelopeDraft(id: string): Promise<void> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to delete SPE draft: ${detail}`);
  }
}
