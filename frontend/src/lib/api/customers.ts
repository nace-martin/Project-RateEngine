import { API_BASE_URL, resolveAuthToken, parseErrorResponse, getJson, sendJson } from "./shared";
import type { Customer } from "../types";

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

export interface CustomerDiscountBulkLine {
  id?: string;
  product_code: string;
  discount_type: DiscountType;
  discount_value: string;
  currency: string;
  min_charge?: string | null;
  max_charge?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  notes?: string | null;
}

export interface ProductCodeOption {
  id: number | string;
  code: string;
  description: string;
  domain: string;
  category: string;
  default_unit?: string;
}

export async function getCustomer(tokenOverride: string | null | undefined, customerId: string): Promise<Customer> {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + `/api/v3/customer-details/${customerId}/`;
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
  const url = API_BASE_URL + `/api/v3/customer-details/${customerId}/`;
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

export async function deleteCustomer(
  tokenOverride: string | null | undefined,
  customerId: string,
): Promise<void> {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + `/api/v3/customer-details/${customerId}/`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Token ${token}`,
    },
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to delete customer: ${detail}`);
  }
}

export async function setCustomerArchived(
  tokenOverride: string | null | undefined,
  customerId: string,
  archived: boolean,
): Promise<Customer> {
  const token = resolveAuthToken(tokenOverride);
  const url = API_BASE_URL + `/api/v3/customer-details/${customerId}/`;
  const response = await fetch(url, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Token ${token}`,
    },
    body: JSON.stringify({ is_active: !archived }),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to ${archived ? 'archive' : 'restore'} customer: ${detail}`);
  }

  return response.json();
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
  try {
    return await getJson<CustomerDiscount[]>(url.toString());
  } catch {
    throw new Error('Failed to fetch customer discounts');
  }
}

export async function createCustomerDiscount(data: Partial<CustomerDiscount>): Promise<CustomerDiscount> {
  try {
    return await sendJson<CustomerDiscount>(API_BASE_URL + '/api/v4/discounts/', 'POST', data);
  } catch (error) {
    throw new Error(`Failed to create discount: ${(error as Error).message}`);
  }
}

export async function updateCustomerDiscount(id: string, data: Partial<CustomerDiscount>): Promise<CustomerDiscount> {
  try {
    return await sendJson<CustomerDiscount>(API_BASE_URL + `/api/v4/discounts/${id}/`, 'PATCH', data);
  } catch (error) {
    throw new Error(`Failed to update discount: ${(error as Error).message}`);
  }
}

export async function deleteCustomerDiscount(id: string): Promise<void> {
  try {
    await sendJson<void>(API_BASE_URL + `/api/v4/discounts/${id}/`, 'DELETE');
  } catch (error) {
    throw new Error(`Failed to delete discount: ${(error as Error).message}`);
  }
}

export async function bulkUpsertCustomerDiscounts(payload: {
  customer: string;
  lines: CustomerDiscountBulkLine[];
}): Promise<{ customer: string; saved_count: number; discounts: CustomerDiscount[] }> {
  try {
    return await sendJson(API_BASE_URL + '/api/v4/discounts/bulk-upsert/', 'POST', payload);
  } catch (error) {
    throw new Error(`Failed to save negotiated pricing: ${(error as Error).message}`);
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
  try {
    return await getJson<ProductCodeOption[]>(url.toString());
  } catch {
    throw new Error('Failed to fetch product codes');
  }
}
