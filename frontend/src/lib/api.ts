import axios from 'axios';
import { Quotation } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api';

// Create a configured axios instance
export const api = axios.create({
  baseURL: API_BASE,
});

async function getAuthToken() {
    return localStorage.getItem('authToken');
}

export async function listCustomers() {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/customers/`, {
        headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
        },
    });
    if (!res.ok) {
        throw new Error('Failed to fetch customers');
    }
    return res.json();
}

export async function createQuotation(quotation: Partial<Quotation>) {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/quotations/`, {
        method: 'POST',
        headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(quotation),
    });
    if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to create quotation');
    }
    return res.json();
}

export async function listStations() {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/stations/`, {
        headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
        },
    });
    if (!res.ok) {
        throw new Error('Failed to fetch stations');
    }
    return res.json();
}

export async function createQuoteVersion(quotationId: number, versionData: any) {
    const token = await getAuthToken();
    const res = await fetch(`${API_BASE}/quotes/${quotationId}/versions`, {
        method: 'POST',
        headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(versionData),
    });
    if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to create quote version');
    }
    return res.json();
}