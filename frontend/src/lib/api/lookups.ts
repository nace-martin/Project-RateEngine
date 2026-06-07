import { API_BASE_URL, getToken, getJson } from './shared';
import type { AirportSearchResult, CountryOption, CityOption } from '../types';

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

export async function listCountries(query?: string): Promise<CountryOption[]> {
  const url = new URL(API_BASE_URL + '/api/v3/core/countries/');
  if (query && query.trim()) {
    url.searchParams.append('q', query.trim());
  }
  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Token ${getToken()}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch countries');
  }

  return response.json();
}

export async function listCities(params?: {
  country_code?: string;
  query?: string;
}): Promise<CityOption[]> {
  const url = new URL(API_BASE_URL + '/api/v3/core/cities/');
  if (params?.country_code) {
    url.searchParams.append('country', params.country_code);
  }
  if (params?.query && params.query.trim()) {
    url.searchParams.append('q', params.query.trim());
  }
  try {
    return await getJson<CityOption[]>(url.toString());
  } catch {
    throw new Error('Failed to fetch cities');
  }
}
