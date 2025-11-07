// frontend/src/lib/api.ts

import { API_BASE_URL } from './config';
import {
  LoginData,
  User,
  Company,
  CompanySearchResult,
  Contact,
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
  RatecardFile,
} from './types';

// Helper to get the token
const getToken = (): string | null => {
  if (typeof window === 'undefined') {
    return null;
  }
  return localStorage.getItem('authToken');
};

// --- Auth ---

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

  const result = await response.json();
  return result;
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

// --- Quotes V3 ---

export async function getQuotesV3(): Promise<V3QuoteComputeResponse[]> {
  const url = API_BASE_URL + '/api/v3/quotes/';
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
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
      Authorization: `Token ${getToken()}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    const errorData = await response.json();
    console.error('Quote compute error:', errorData);
    throw new Error(
      `Failed to create quote: ${JSON.stringify(errorData.detail) || response.statusText}`,
    );
  }

  return response.json();
}

export async function getQuoteV3(
  quoteId: string,
): Promise<V3QuoteComputeResponse> {
  const url = API_BASE_URL + `/api/v3/quotes/${quoteId}/`;
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${getToken()}`,
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
): Promise<RatecardFile> {
  const url = API_BASE_URL + '/api/v3/ratecards/upload/';
  const formData = new FormData();
  formData.append('file', file);
  formData.append('supplier_id', supplierId);

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Token ${getToken()}`,
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
