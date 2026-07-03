// frontend/src/lib/api.ts
import axios from 'axios';
import { API_BASE_URL } from './config';
import { getJson, sendJson } from './api/shared';
import { mapQuoteDetailToComputeResult } from './quote-detail-mapping';
import { ReplyAnalysisResult, SPEChargeLine, SPEConditions, SPECommodity } from './spot-types';
import { DraftQuote, DraftQuoteResolvePayload, DraftQuoteResolveResponse } from './draft-quote-types';
import {
  LoginData,
  User,
  AirportSearchResult,
  CountryOption,
  CityOption,
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
  Customer,
  QuoteVersionCreatePayload,
  QuoteComputeResult,
  OrganizationBrandingSettings,
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

const flattenErrorDetail = (value: unknown, prefix = ''): string[] => {
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenErrorDetail(item, prefix));
  }

  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) => {
      const childPrefix = prefix ? `${prefix}.${key}` : key;
      return flattenErrorDetail(child, childPrefix);
    });
  }

  const message = value == null ? 'Unknown error' : String(value);
  return prefix ? [`${prefix}: ${message}`] : [message];
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
      return flattenErrorDetail(data).join(' | ');
    }
  } catch {
    // ignore parse errors
  }
  return response.statusText || 'Unknown error';
};

const sleep = (ms: number) => new Promise((resolve) => globalThis.setTimeout(resolve, ms));

const isRetryableResponseStatus = (status: number) => [502, 503, 504].includes(status);

const isTransientFetchFailure = (error: unknown) => {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return error.name === 'TypeError' || message.includes('failed to fetch') || message.includes('networkerror');
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
    email:
      ((rawUser && typeof rawUser.email === 'string') ? rawUser.email : undefined) ?? null,
    role:
      ((rawUser && typeof rawUser.role === 'string') ? rawUser.role : undefined) ??
      (typeof result.role === 'string' ? result.role : 'sales'),
    organization:
      rawUser && rawUser.organization && typeof rawUser.organization === 'object'
        ? (rawUser.organization as User['organization'])
        : null,
  };

  return {
    token,
    user: normalizedUser,
  };
}


export async function getOrganizationBrandingSettings(): Promise<OrganizationBrandingSettings> {
  const url = API_BASE_URL + '/api/v3/branding/organization/';
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: 'no-store',
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to load branding settings: ${detail}`);
  }

  return response.json();
}

export async function updateOrganizationBrandingSettings(
  data: Partial<OrganizationBrandingSettings> & {
    logo_primary_file?: File | null;
    logo_small_file?: File | null;
    clear_primary_logo?: boolean;
    clear_small_logo?: boolean;
  },
): Promise<OrganizationBrandingSettings> {
  const url = API_BASE_URL + '/api/v3/branding/organization/';
  const formData = new FormData();

  Object.entries(data).forEach(([key, value]) => {
    if (value === undefined || value === null || key === 'logo_primary_file' || key === 'logo_small_file' || key === 'clear_primary_logo' || key === 'clear_small_logo') {
      return;
    }
    formData.append(key, typeof value === 'boolean' ? String(value) : String(value));
  });

  if (data.logo_primary_file) {
    formData.append('logo_primary', data.logo_primary_file);
  }
  if (data.logo_small_file) {
    formData.append('logo_small', data.logo_small_file);
  }
  if (data.clear_primary_logo) formData.append('clear_primary_logo', 'true');
  if (data.clear_small_logo) formData.append('clear_small_logo', 'true');

  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update branding settings: ${detail}`);
  }

  return response.json();
}

// --- Airport Search ---

export { searchAirports } from './api/lookups';

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
    console.warn('Quote compute validation:', errorData || response.statusText);

    let message = response.statusText || 'Unknown error';
    if (typeof errorData === 'string') {
      message = errorData;
    } else if (errorData && typeof errorData === 'object') {
      const payload = errorData as Record<string, unknown>;
      const detail = typeof payload.detail === 'string' ? payload.detail : null;
      const remediation =
        typeof payload.suggested_remediation === 'string'
          ? payload.suggested_remediation
          : null;
      const errorCode =
        typeof payload.error_code === 'string' ? payload.error_code : null;
      const resolutionReason =
        typeof payload.resolution_reason === 'string'
          ? payload.resolution_reason
          : null;
      const component = typeof payload.component === 'string' ? payload.component : null;
      const missingDimensions = Array.isArray(payload.missing_dimensions)
        ? payload.missing_dimensions.filter((item): item is string => typeof item === 'string')
        : [];

      if (detail) {
        const contextBits: string[] = [];
        if (errorCode) contextBits.push(errorCode);
        if (resolutionReason) contextBits.push(resolutionReason);
        if (component) contextBits.push(`component ${component}`);
        message = contextBits.length > 0 ? `${detail} [${contextBits.join(' | ')}]` : detail;
        if (missingDimensions.length > 0) {
          message = `${message} Missing: ${missingDimensions.join(', ')}.`;
        }
        if (remediation) {
          message = `${message} Suggested action: ${remediation}`;
        }
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





export {
  getCustomer,
  updateCustomer,
} from './api/customers';

export {
  listCountries,
  listCities,
} from './api/lookups';

export {
  deleteCustomer,
  setCustomerArchived,
} from './api/customers';


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

// --- Legacy Rate Card CSV Bridge ---
export async function importRateCardCSV(id: string, file: File): Promise<{ message: string; errors: string[] }> {
  // Legacy UI bridge only. New admin management must use V4 rate endpoints.
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
// SPOT MODE APIs (consolidated; replaces src/lib/api/spot.ts)
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
  data: { charges?: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }>; conditions?: Partial<SPEConditions> }
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
  const authToken = resolveAuthToken();
  const retryDelaysMs = [400, 1200];
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retryDelaysMs.length; attempt += 1) {
    try {
      const response = await fetch(url, {
        headers: {
          Authorization: `Token ${authToken}`,
        },
      });

      if (response.ok) {
        return response.json();
      }

      if (attempt < retryDelaysMs.length && isRetryableResponseStatus(response.status)) {
        await sleep(retryDelaysMs[attempt]);
        continue;
      }

      const detail = await parseErrorResponse(response);
      throw new Error(`Failed to get SPE: ${detail}`);
    } catch (error) {
      if (attempt < retryDelaysMs.length && isTransientFetchFailure(error)) {
        await sleep(retryDelaysMs[attempt]);
        continue;
      }

      lastError = error instanceof Error ? error : new Error('Failed to get SPE.');
      break;
    }
  }

  throw lastError || new Error('Failed to get SPE.');
}

/**
 * Fetch Draft Quote contract payload for an existing SPOT envelope.
 */
export async function getDraftQuote(id: string): Promise<DraftQuote> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${id}/draft-quote/`;
  const authToken = resolveAuthToken();
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${authToken}`,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch draft quote: ${detail}`);
  }

  return response.json();
}


/**
 * Submit operator decisions to resolve exceptions for a draft quote.
 */
export async function resolveDraftQuoteDecisions(
  envelopeId: string,
  payload: DraftQuoteResolvePayload
): Promise<DraftQuoteResolveResponse> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${envelopeId}/draft-quote/resolve/`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to resolve draft quote decisions: ${detail}`);
  }

  return response.json() as Promise<DraftQuoteResolveResponse>;
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

export async function reviewSpotSourceBatch(
  envelopeId: string,
  sourceBatchId: string,
  request: { reviewed_safe_to_quote: boolean; review_note?: string }
): Promise<SpotPricingEnvelope> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${envelopeId}/sources/${sourceBatchId}/review/`;
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
    throw new Error(`Source review failed: ${detail}`);
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
  options: {
    text?: string;
    file?: File | null;
    assertions?: import('./spot-types').ExtractedAssertion[];
    speId?: string;
    sourceBatchId?: string;
    sourceKind?: 'AIRLINE' | 'AGENT' | 'MANUAL' | 'OTHER';
    targetBucket?: 'airfreight' | 'origin_charges' | 'destination_charges' | 'mixed';
    label?: string;
    sourceReference?: string;
    useAi?: boolean;
    structuredIntake?: Record<string, unknown>;
  }
): Promise<ReplyAnalysisResult> {
  const {
    text = '',
    file = null,
    assertions = [],
    speId,
    sourceBatchId,
    sourceKind,
    targetBucket,
    label,
    sourceReference,
    useAi = true,
    structuredIntake,
  } = options;
  const url = API_BASE_URL + '/api/v3/spot/analyze-reply/';
  const formData = new FormData();

  if (text.trim()) {
    formData.append('text', text);
  }
  if (file) {
    formData.append('file', file);
  }
  if (assertions.length > 0) {
    formData.append('assertions', JSON.stringify(assertions));
  }
  if (speId) {
    formData.append('spe_id', speId);
  }
  if (sourceBatchId) {
    formData.append('source_batch_id', sourceBatchId);
  }
  if (sourceKind) {
    formData.append('source_kind', sourceKind);
  }
  if (targetBucket) {
    formData.append('target_bucket', targetBucket);
  }
  if (label) {
    formData.append('label', label);
  }
  if (sourceReference) {
    formData.append('source_reference', sourceReference);
  }
  if (structuredIntake) {
    formData.append('structured_intake', JSON.stringify(structuredIntake));
  }
  formData.append('use_ai', String(useAi));

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: formData,
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
  payment_term: 'PREPAID' | 'COLLECT';
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
    contact_id?: string;
    incoterm?: string;
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

export {
  getDashboardMetrics,
  getFunnelMetrics,
  getRevenueMargin,
  getUserPerformance,
  exportReportData,
  getTier1Stats,
} from './api/reports';

export type {
  DashboardTimeframe,
  DashboardMetricsData,
  ReportFilters,
  FunnelMetricsData,
  ModeBreakdown,
  RevenueMarginData,
  UserPerformanceItem,
  UserPerformanceData,
} from './api/reports';

// =============================================================================
// Customer Discounts API
// =============================================================================

export {
  getCustomerDiscounts,
  createCustomerDiscount,
  updateCustomerDiscount,
  deleteCustomerDiscount,
  bulkUpsertCustomerDiscounts,
  getProductCodes,
  createProductCodeRequest,
  getProductCodeRequests,
  approveProductCodeRequest,
  rejectProductCodeRequest,
} from './api/customers';

export type {
  DiscountType,
  CustomerDiscount,
  CustomerDiscountBulkLine,
  ProductCodeOption,
  ProductCodeRequestPayload,
  ProductCodeRequestResponse,
} from './api/customers';


// =============================================================================
// V4 SELL RATES API
// =============================================================================

export interface PricingReferenceOption {
  id: number;
  code: string;
  name: string;
}

export interface PricingAgentOption extends PricingReferenceOption {
  country_code: string;
  agent_type: string;
}

export interface PricingCarrierOption extends PricingReferenceOption {
  carrier_type: string;
}

export interface QuoteCounterpartyHints {
  direction: 'IMPORT' | 'EXPORT' | 'DOMESTIC';
  service_scope: 'A2A' | 'D2A' | 'A2D' | 'D2D';
  origin_airport: string;
  destination_airport: string;
  buy_currency: string | null;
  quote_date: string;
  required_components: string[];
  available_counterparty_types: Array<'agent' | 'carrier'>;
  recommended_counterparty_type: 'agent' | 'carrier' | null;
  component_counterparty_types: Record<string, Array<'agent' | 'carrier'>>;
  agents: PricingAgentOption[];
  carriers: PricingCarrierOption[];
  advisory: string;
}

export interface RateWeightBreak {
  min_kg: number | string;
  rate: string;
}

export interface EffectiveDatedRateRecord {
  id: number;
  product_code: number;
  product_code_code: string;
  product_code_description: string;
  currency: string;
  valid_from: string;
  valid_until: string;
  created_at: string;
  updated_at: string;
  created_by?: number | null;
  created_by_username?: string | null;
  updated_by?: number | null;
  updated_by_username?: string | null;
  lineage_id?: string | null;
  supersedes_rate?: number | null;
  is_active: boolean;
}

export type RateChangeAction = 'CREATE' | 'UPDATE' | 'RETIRE' | 'DELETE' | 'REVISE';

export interface RateChangeLogEntry {
  id: number;
  table_name: string;
  object_pk: string;
  actor: number | null;
  actor_username: string | null;
  action: RateChangeAction;
  lineage_id: string | null;
  before_snapshot: Record<string, unknown> | null;
  after_snapshot: Record<string, unknown> | null;
  created_at: string;
}

export interface CounterpartyRateRecord {
  agent: number | null;
  agent_name: string | null;
  carrier: number | null;
  carrier_name: string | null;
}

export interface LaneRateRecord extends EffectiveDatedRateRecord {
  origin_airport?: string | null;
  destination_airport?: string | null;
  origin_zone?: string | null;
  destination_zone?: string | null;
  rate_per_kg: string | null;
  rate_per_shipment: string | null;
  min_charge: string | null;
  max_charge: string | null;
  is_additive: boolean;
  percent_rate?: string | null;
  weight_breaks: RateWeightBreak[] | null;
}

export interface LaneCOGSRateRecord extends LaneRateRecord, CounterpartyRateRecord {
}

export interface LocalRateRecord extends EffectiveDatedRateRecord {
  location: string;
  direction: 'EXPORT' | 'IMPORT';
  payment_term?: 'PREPAID' | 'COLLECT' | 'ANY';
  rate_type: 'FIXED' | 'PER_KG' | 'PERCENT';
  amount: string;
  is_additive: boolean;
  additive_flat_amount: string | null;
  min_charge: string | null;
  max_charge: string | null;
  weight_breaks: RateWeightBreak[] | null;
  percent_of_product_code: number | null;
  percent_of_product_code_code: string | null;
  percent_of_product_code_description: string | null;
}

export interface LocalCOGSRateRecord extends LocalRateRecord, CounterpartyRateRecord {}

export type V4SellRate = LaneRateRecord;
export type ImportCOGSRate = LaneCOGSRateRecord;
export type ImportCOGSUpsertPayload = LaneRateUpsertPayload;

export interface LaneRateUpsertPayload {
  product_code: number;
  origin_airport?: string;
  destination_airport?: string;
  origin_zone?: string;
  destination_zone?: string;
  agent?: number | null;
  carrier?: number | null;
  currency: string;
  rate_per_kg?: string | null;
  rate_per_shipment?: string | null;
  min_charge?: string | null;
  max_charge?: string | null;
  is_additive?: boolean;
  percent_rate?: string | null;
  weight_breaks?: RateWeightBreak[] | null;
  valid_from: string;
  valid_until: string;
}

export interface LocalRateUpsertPayload {
  product_code: number;
  location: string;
  direction: 'EXPORT' | 'IMPORT';
  payment_term?: 'PREPAID' | 'COLLECT' | 'ANY';
  agent?: number | null;
  carrier?: number | null;
  currency: string;
  rate_type: 'FIXED' | 'PER_KG' | 'PERCENT';
  amount: string;
  is_additive?: boolean;
  additive_flat_amount?: string | null;
  min_charge?: string | null;
  max_charge?: string | null;
  weight_breaks?: RateWeightBreak[] | null;
  percent_of_product_code?: number | null;
  valid_from: string;
  valid_until: string;
}

export interface RateRevisionOptions {
  retire_previous?: boolean;
}

export interface V4RateListParams {
  search?: string;
  origin?: string;
  destination?: string;
  location?: string;
  direction?: string;
  paymentTerm?: string;
  productCode?: string | number;
  currency?: string;
  agent?: string | number;
  carrier?: string | number;
  status?: 'active' | 'expired' | 'scheduled';
  validOn?: string;
}

export async function listPricingAgents(params?: {
  search?: string;
}): Promise<PricingAgentOption[]> {
  const url = new URL(API_BASE_URL + '/api/v4/agents/');
  if (params?.search) url.searchParams.append('search', params.search);
  try {
    return await getJson<PricingAgentOption[]>(url.toString());
  } catch {
    throw new Error('Failed to fetch pricing agents');
  }
}

export async function manuallyResolveSpotChargeLine(
  envelopeId: string,
  chargeLineId: string,
  request: { manual_resolved_product_code_id: number | string }
): Promise<SPEChargeLine> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${envelopeId}/charges/${chargeLineId}/manual-resolution/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Manual charge review failed: ${detail}`);
  }

  return response.json();
}

export async function resolveSpotConditionalChargeLine(
  envelopeId: string,
  chargeLineId: string,
  request: { action: 'KEEP' | 'REMOVE' }
): Promise<SpotPricingEnvelope> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${envelopeId}/charges/${chargeLineId}/conditional-resolution/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Conditional charge review failed: ${detail}`);
  }

  return response.json();
}

export async function listPricingCarriers(params?: {
  search?: string;
}): Promise<PricingCarrierOption[]> {
  const url = new URL(API_BASE_URL + '/api/v4/carriers/');
  if (params?.search) url.searchParams.append('search', params.search);
  try {
    return await getJson<PricingCarrierOption[]>(url.toString());
  } catch {
    throw new Error('Failed to fetch pricing carriers');
  }
}

export async function getQuoteCounterpartyHints(params: {
  direction: 'IMPORT' | 'EXPORT' | 'DOMESTIC';
  serviceScope: 'A2A' | 'D2A' | 'A2D' | 'D2D';
  originAirport: string;
  destinationAirport: string;
  buyCurrency?: string | null;
  quoteDate?: string;
}): Promise<QuoteCounterpartyHints> {
  const url = new URL(API_BASE_URL + '/api/v4/quote/counterparty-hints/');
  url.searchParams.append('direction', params.direction);
  url.searchParams.append('service_scope', params.serviceScope);
  url.searchParams.append('origin_airport', params.originAirport);
  url.searchParams.append('destination_airport', params.destinationAirport);
  if (params.buyCurrency) url.searchParams.append('buy_currency', params.buyCurrency);
  if (params.quoteDate) url.searchParams.append('quote_date', params.quoteDate);

  try {
    return await getJson<QuoteCounterpartyHints>(url.toString());
  } catch (error) {
    throw new Error(`Failed to fetch quote counterparty hints: ${(error as Error).message}`);
  }
}

function appendRateListParams(
  url: URL,
  params: V4RateListParams | undefined,
  routeParamNames?: { origin?: string; destination?: string },
) {
  if (!params) return;
  if (params.search) url.searchParams.append('search', params.search);
  if (params.origin && routeParamNames?.origin) url.searchParams.append(routeParamNames.origin, params.origin);
  if (params.destination && routeParamNames?.destination) url.searchParams.append(routeParamNames.destination, params.destination);
  if (params.location) url.searchParams.append('location', params.location);
  if (params.direction) url.searchParams.append('direction', params.direction);
  if (params.paymentTerm) url.searchParams.append('payment_term', params.paymentTerm);
  if (params.productCode !== undefined) url.searchParams.append('product_code', String(params.productCode));
  if (params.currency) url.searchParams.append('currency', params.currency);
  if (params.agent !== undefined) url.searchParams.append('agent', String(params.agent));
  if (params.carrier !== undefined) url.searchParams.append('carrier', String(params.carrier));
  if (params.status) url.searchParams.append('status', params.status);
  if (params.validOn) url.searchParams.append('valid_on', params.validOn);
}

async function listRateRows<T>(
  path: string,
  params?: V4RateListParams,
  routeParamNames?: { origin?: string; destination?: string },
): Promise<T[]> {
  const url = new URL(API_BASE_URL + path);
  appendRateListParams(url, params, routeParamNames);
  try {
    return await getJson<T[]>(url.toString());
  } catch (error) {
    throw new Error(`Failed to fetch rates: ${(error as Error).message}`);
  }
}

async function createRateRow<TResponse, TPayload>(path: string, data: TPayload): Promise<TResponse> {
  const response = await fetch(API_BASE_URL + path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create rate: ${detail}`);
  }
  return response.json();
}

async function updateRateRow<TResponse, TPayload>(path: string, data: Partial<TPayload>): Promise<TResponse> {
  const response = await fetch(API_BASE_URL + path, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to update rate: ${detail}`);
  }
  return response.json();
}

async function retireRateRow<TResponse>(path: string): Promise<TResponse> {
  const response = await fetch(API_BASE_URL + path, {
    method: 'POST',
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to retire rate: ${detail}`);
  }
  return response.json();
}

async function reviseRateRow<TResponse, TPayload>(
  path: string,
  data: TPayload & RateRevisionOptions,
): Promise<TResponse> {
  const response = await fetch(API_BASE_URL + path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to revise rate: ${detail}`);
  }
  return response.json();
}

async function listRateHistory(path: string): Promise<RateChangeLogEntry[]> {
  const response = await fetch(API_BASE_URL + path, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to fetch rate history: ${detail}`);
  }
  return response.json();
}

export async function listExportSellRates(params?: V4RateListParams): Promise<LaneRateRecord[]> {
  return listRateRows<LaneRateRecord>('/api/v4/rates/export/', params, {
    origin: 'origin_airport',
    destination: 'destination_airport',
  });
}

export async function createExportSellRate(data: LaneRateUpsertPayload): Promise<LaneRateRecord> {
  return createRateRow<LaneRateRecord, LaneRateUpsertPayload>('/api/v4/rates/export/', data);
}

export async function updateExportSellRate(id: number | string, data: Partial<LaneRateUpsertPayload>): Promise<LaneRateRecord> {
  return updateRateRow<LaneRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/export/${id}/`, data);
}

export async function retireExportSellRate(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LaneRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LaneRateRecord>(`/api/v4/rates/export/${id}/retire/`);
}

export async function reviseExportSellRate(
  id: number | string,
  data: LaneRateUpsertPayload & RateRevisionOptions,
): Promise<LaneRateRecord> {
  return reviseRateRow<LaneRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/export/${id}/revise/`, data);
}

export async function getExportSellRateHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/export/${id}/history/`);
}

export async function listImportSellRates(params?: V4RateListParams): Promise<LaneRateRecord[]> {
  return listRateRows<LaneRateRecord>('/api/v4/rates/import/', params, {
    origin: 'origin_airport',
    destination: 'destination_airport',
  });
}

export async function createImportSellRate(data: LaneRateUpsertPayload): Promise<LaneRateRecord> {
  return createRateRow<LaneRateRecord, LaneRateUpsertPayload>('/api/v4/rates/import/', data);
}

export async function updateImportSellRate(id: number | string, data: Partial<LaneRateUpsertPayload>): Promise<LaneRateRecord> {
  return updateRateRow<LaneRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/import/${id}/`, data);
}

export async function retireImportSellRate(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LaneRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LaneRateRecord>(`/api/v4/rates/import/${id}/retire/`);
}

export async function reviseImportSellRate(
  id: number | string,
  data: LaneRateUpsertPayload & RateRevisionOptions,
): Promise<LaneRateRecord> {
  return reviseRateRow<LaneRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/import/${id}/revise/`, data);
}

export async function getImportSellRateHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/import/${id}/history/`);
}

export async function listExportCOGS(params?: V4RateListParams): Promise<LaneCOGSRateRecord[]> {
  return listRateRows<LaneCOGSRateRecord>('/api/v4/rates/export-cogs/', params, {
    origin: 'origin_airport',
    destination: 'destination_airport',
  });
}

export async function createExportCOGS(data: LaneRateUpsertPayload): Promise<LaneCOGSRateRecord> {
  return createRateRow<LaneCOGSRateRecord, LaneRateUpsertPayload>('/api/v4/rates/export-cogs/', data);
}

export async function updateExportCOGS(id: number | string, data: Partial<LaneRateUpsertPayload>): Promise<LaneCOGSRateRecord> {
  return updateRateRow<LaneCOGSRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/export-cogs/${id}/`, data);
}

export async function retireExportCOGS(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LaneCOGSRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LaneCOGSRateRecord>(`/api/v4/rates/export-cogs/${id}/retire/`);
}

export async function reviseExportCOGS(
  id: number | string,
  data: LaneRateUpsertPayload & RateRevisionOptions,
): Promise<LaneCOGSRateRecord> {
  return reviseRateRow<LaneCOGSRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/export-cogs/${id}/revise/`, data);
}

export async function getExportCOGSHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/export-cogs/${id}/history/`);
}

export async function listImportCOGS(params?: V4RateListParams): Promise<ImportCOGSRate[]> {
  return listRateRows<ImportCOGSRate>('/api/v4/rates/import-cogs/', params, {
    origin: 'origin_airport',
    destination: 'destination_airport',
  });
}

export async function createImportCOGS(data: ImportCOGSUpsertPayload): Promise<ImportCOGSRate> {
  return createRateRow<ImportCOGSRate, ImportCOGSUpsertPayload>('/api/v4/rates/import-cogs/', data);
}

export async function updateImportCOGS(id: number | string, data: Partial<ImportCOGSUpsertPayload>): Promise<ImportCOGSRate> {
  return updateRateRow<ImportCOGSRate, ImportCOGSUpsertPayload>(`/api/v4/rates/import-cogs/${id}/`, data);
}

export async function retireImportCOGS(id: number | string): Promise<{ deleted?: boolean; detail?: string } | ImportCOGSRate> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | ImportCOGSRate>(`/api/v4/rates/import-cogs/${id}/retire/`);
}

export async function reviseImportCOGS(
  id: number | string,
  data: ImportCOGSUpsertPayload & RateRevisionOptions,
): Promise<ImportCOGSRate> {
  return reviseRateRow<ImportCOGSRate, ImportCOGSUpsertPayload>(`/api/v4/rates/import-cogs/${id}/revise/`, data);
}

export async function getImportCOGSHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/import-cogs/${id}/history/`);
}

export async function listDomesticSellRates(params?: V4RateListParams): Promise<LaneRateRecord[]> {
  return listRateRows<LaneRateRecord>('/api/v4/rates/domestic/', params, {
    origin: 'origin_zone',
    destination: 'destination_zone',
  });
}

export async function createDomesticSellRate(data: LaneRateUpsertPayload): Promise<LaneRateRecord> {
  return createRateRow<LaneRateRecord, LaneRateUpsertPayload>('/api/v4/rates/domestic/', data);
}

export async function updateDomesticSellRate(id: number | string, data: Partial<LaneRateUpsertPayload>): Promise<LaneRateRecord> {
  return updateRateRow<LaneRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/domestic/${id}/`, data);
}

export async function retireDomesticSellRate(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LaneRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LaneRateRecord>(`/api/v4/rates/domestic/${id}/retire/`);
}

export async function reviseDomesticSellRate(
  id: number | string,
  data: LaneRateUpsertPayload & RateRevisionOptions,
): Promise<LaneRateRecord> {
  return reviseRateRow<LaneRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/domestic/${id}/revise/`, data);
}

export async function getDomesticSellRateHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/domestic/${id}/history/`);
}

export async function listDomesticCOGS(params?: V4RateListParams): Promise<LaneCOGSRateRecord[]> {
  return listRateRows<LaneCOGSRateRecord>('/api/v4/rates/domestic-cogs/', params, {
    origin: 'origin_zone',
    destination: 'destination_zone',
  });
}

export async function createDomesticCOGS(data: LaneRateUpsertPayload): Promise<LaneCOGSRateRecord> {
  return createRateRow<LaneCOGSRateRecord, LaneRateUpsertPayload>('/api/v4/rates/domestic-cogs/', data);
}

export async function updateDomesticCOGS(id: number | string, data: Partial<LaneRateUpsertPayload>): Promise<LaneCOGSRateRecord> {
  return updateRateRow<LaneCOGSRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/domestic-cogs/${id}/`, data);
}

export async function retireDomesticCOGS(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LaneCOGSRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LaneCOGSRateRecord>(`/api/v4/rates/domestic-cogs/${id}/retire/`);
}

export async function reviseDomesticCOGS(
  id: number | string,
  data: LaneRateUpsertPayload & RateRevisionOptions,
): Promise<LaneCOGSRateRecord> {
  return reviseRateRow<LaneCOGSRateRecord, LaneRateUpsertPayload>(`/api/v4/rates/domestic-cogs/${id}/revise/`, data);
}

export async function getDomesticCOGSHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/domestic-cogs/${id}/history/`);
}

export async function listLocalSellRates(params?: V4RateListParams): Promise<LocalRateRecord[]> {
  return listRateRows<LocalRateRecord>('/api/v4/rates/local-sell/', params);
}

export async function createLocalSellRate(data: LocalRateUpsertPayload): Promise<LocalRateRecord> {
  return createRateRow<LocalRateRecord, LocalRateUpsertPayload>('/api/v4/rates/local-sell/', data);
}

export async function updateLocalSellRate(id: number | string, data: Partial<LocalRateUpsertPayload>): Promise<LocalRateRecord> {
  return updateRateRow<LocalRateRecord, LocalRateUpsertPayload>(`/api/v4/rates/local-sell/${id}/`, data);
}

export async function retireLocalSellRate(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LocalRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LocalRateRecord>(`/api/v4/rates/local-sell/${id}/retire/`);
}

export async function reviseLocalSellRate(
  id: number | string,
  data: LocalRateUpsertPayload & RateRevisionOptions,
): Promise<LocalRateRecord> {
  return reviseRateRow<LocalRateRecord, LocalRateUpsertPayload>(`/api/v4/rates/local-sell/${id}/revise/`, data);
}

export async function getLocalSellRateHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/local-sell/${id}/history/`);
}

export async function listLocalCOGSRates(params?: V4RateListParams): Promise<LocalCOGSRateRecord[]> {
  return listRateRows<LocalCOGSRateRecord>('/api/v4/rates/local-cogs/', params);
}

export async function createLocalCOGSRate(data: LocalRateUpsertPayload): Promise<LocalCOGSRateRecord> {
  return createRateRow<LocalCOGSRateRecord, LocalRateUpsertPayload>('/api/v4/rates/local-cogs/', data);
}

export async function updateLocalCOGSRate(id: number | string, data: Partial<LocalRateUpsertPayload>): Promise<LocalCOGSRateRecord> {
  return updateRateRow<LocalCOGSRateRecord, LocalRateUpsertPayload>(`/api/v4/rates/local-cogs/${id}/`, data);
}

export async function retireLocalCOGSRate(id: number | string): Promise<{ deleted?: boolean; detail?: string } | LocalCOGSRateRecord> {
  return retireRateRow<{ deleted?: boolean; detail?: string } | LocalCOGSRateRecord>(`/api/v4/rates/local-cogs/${id}/retire/`);
}

export async function reviseLocalCOGSRate(
  id: number | string,
  data: LocalRateUpsertPayload & RateRevisionOptions,
): Promise<LocalCOGSRateRecord> {
  return reviseRateRow<LocalCOGSRateRecord, LocalRateUpsertPayload>(`/api/v4/rates/local-cogs/${id}/revise/`, data);
}

export async function getLocalCOGSRateHistory(id: number | string): Promise<RateChangeLogEntry[]> {
  return listRateHistory(`/api/v4/rates/local-cogs/${id}/history/`);
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
  pricing_model: string;
  source_tables: string[];
  notes: string[];
  lines: LogicalRateCardLine[];
  line_count: number;
  currencies: string[];
  coverage: string[];
}

export interface LogicalRateCardLine {
  id: string;
  source_table: string;
  source_label: string;
  pricing_role: string;
  product_code: number;
  product_code_code: string;
  product_code_description: string;
  currency: string | null;
  coverage_label: string | null;
  origin_code: string | null;
  destination_code: string | null;
  location_code: string | null;
  direction: string | null;
  payment_term: string | null;
  rate_type: string | null;
  rate_per_kg: string | null;
  rate_per_shipment: string | null;
  amount: string | null;
  min_charge: string | null;
  max_charge: string | null;
  percent_rate: string | null;
  weight_breaks: { min_kg: number; rate: string }[] | null;
  is_additive: boolean;
  valid_from: string;
  valid_until: string;
  counterparty: string | null;
}

export interface V4RateCardUploadSuccessResponse {
  success: true;
  dry_run?: false;
  message: string;
  processed_rows: number;
  created_rows: number;
  updated_rows: number;
}

export interface V4RateCardUploadPreviewRow {
  row_number: number;
  table_name: string;
  action: 'CREATE' | 'UPDATE';
  product_code: string;
  coverage: string;
  currency: string;
  valid_from: string;
  valid_until: string;
}

export interface V4RateCardUploadPreviewResponse {
  success: true;
  dry_run: true;
  message: string;
  processed_rows: number;
  created_rows: number;
  updated_rows: number;
  preview_rows: V4RateCardUploadPreviewRow[];
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

export async function uploadV4RateCardCSV(
  file: File,
  options?: { dryRun?: boolean },
): Promise<V4RateCardUploadSuccessResponse | V4RateCardUploadPreviewResponse> {
  const url = API_BASE_URL + '/api/v4/rates/upload/';
  const formData = new FormData();
  formData.append('file', file);
  if (options?.dryRun) {
    formData.append('dry_run', 'true');
  }

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
    return payload as V4RateCardUploadSuccessResponse | V4RateCardUploadPreviewResponse;
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

export interface SpotFindingReviewRequest {
  finding_code: string;
  canonical_type: string | null;
  template_line_id: number | null;
  charge_line_id: string | null;
  comment?: string | null;
}

export async function reviewSpotFinding(
  envelopeId: string,
  request: SpotFindingReviewRequest
): Promise<unknown> {
  const url = API_BASE_URL + `/api/v3/spot/envelopes/${envelopeId}/findings/reviewed/`;
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
    throw new Error(`Reviewing finding failed: ${detail}`);
  }

  return response.json();
}

export * from './api/spot-validation';


