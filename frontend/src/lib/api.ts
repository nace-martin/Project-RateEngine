import { Quotation } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000/api';

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
