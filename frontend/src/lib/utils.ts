import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Extract a human-readable error message from various API error shapes
export function extractErrorMessage(data: unknown, fallback = 'Request failed'): string {
  if (typeof data === 'string') return data || fallback;
  if (data && typeof data === 'object') {
    const anyData: any = data as any;
    if (typeof anyData.detail === 'string' && anyData.detail) return anyData.detail;
    if (Array.isArray(anyData.non_field_errors) && anyData.non_field_errors.length) {
      return anyData.non_field_errors.join(' ');
    }
    try {
      const parts: string[] = [];
      for (const v of Object.values(anyData)) {
        if (typeof v === 'string') parts.push(v);
        else if (Array.isArray(v)) {
          for (const item of v) parts.push(typeof item === 'string' ? item : JSON.stringify(item));
        }
      }
      if (parts.length) return parts.join(' ');
    } catch {}
  }
  return fallback;
}

// Convenience: parse a fetch Response and extract a message
export async function extractErrorFromResponse(res: Response, fallback = 'Request failed'): Promise<string> {
  try {
    const body = await res.json();
    return extractErrorMessage(body, res.statusText || fallback);
  } catch {
    return res.statusText || fallback;
  }
}
