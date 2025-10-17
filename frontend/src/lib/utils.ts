import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export async function extractErrorFromResponse(response: Response, defaultMessage: string): Promise<string> {
  if (response.ok) {
    return defaultMessage;
  }

  try {
    const errorData = await response.json();
    return errorData.detail || errorData.error || defaultMessage;
  } catch {
    return defaultMessage;
  }
}
