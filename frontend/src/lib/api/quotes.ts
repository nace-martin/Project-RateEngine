import type {
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
} from "../types";
import { API_BASE_URL, resolveAuthToken } from "./shared";

export async function computeQuoteV3(
  data: V3QuoteComputeRequest,
): Promise<V3QuoteComputeResponse> {
  const url = API_BASE_URL + "/api/v3/quotes/compute/";
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
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
    console.error("Quote compute error:", errorData || response.statusText);

    let message = response.statusText || "Unknown error";
    if (typeof errorData === "string") {
      message = errorData;
    } else if (errorData && typeof errorData === "object") {
      const payload = errorData as Record<string, unknown>;
      if ("detail" in payload && typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Object.keys(payload).length > 0) {
        message = JSON.stringify(payload);
      }
    }

    throw new Error(`Failed to create quote: ${message}`);
  }

  return response.json();
}
