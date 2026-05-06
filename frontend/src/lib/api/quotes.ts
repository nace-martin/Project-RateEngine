import type {
  V3QuoteComputeRequest,
  V3QuoteComputeResponse,
} from "../types";
import { API_BASE_URL, resolveAuthToken } from "./shared";

function formatQuoteComputeError(
  errorData: unknown,
  statusText: string,
): string {
  let message = statusText || "Unknown error";

  if (typeof errorData === "string") {
    return errorData;
  }

  if (!errorData || typeof errorData !== "object") {
    return message;
  }

  const payload = errorData as Record<string, unknown>;
  const detail = typeof payload.detail === "string" ? payload.detail : null;
  const remediation =
    typeof payload.suggested_remediation === "string"
      ? payload.suggested_remediation
      : null;
  const errorCode =
    typeof payload.error_code === "string" ? payload.error_code : null;
  const resolutionReason =
    typeof payload.resolution_reason === "string"
      ? payload.resolution_reason
      : null;
  const component = typeof payload.component === "string" ? payload.component : null;
  const missingDimensions = Array.isArray(payload.missing_dimensions)
    ? payload.missing_dimensions.filter((item): item is string => typeof item === "string")
    : [];

  if (!detail) {
    return Object.keys(payload).length > 0 ? JSON.stringify(payload) : message;
  }

  const contextBits: string[] = [];
  if (errorCode) contextBits.push(errorCode);
  if (resolutionReason) contextBits.push(resolutionReason);
  if (component) contextBits.push(`component ${component}`);

  if (contextBits.length > 0) {
    message = `${detail} [${contextBits.join(" | ")}]`;
  } else {
    message = detail;
  }

  if (missingDimensions.length > 0) {
    message = `${message} Missing: ${missingDimensions.join(", ")}.`;
  }

  if (remediation) {
    message = `${message} Suggested action: ${remediation}`;
  }

  return message;
}

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
    console.warn("Quote compute validation:", errorData || response.statusText);
    const message = formatQuoteComputeError(errorData, response.statusText);

    throw new Error(`Failed to create quote: ${message}`);
  }

  return response.json();
}
