const rawApiBase = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export const API_BASE_URL = rawApiBase.toLowerCase().endsWith('/api')
  ? rawApiBase.slice(0, -4)
  : rawApiBase;
