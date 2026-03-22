import type {
  CreateSPERequest,
  ScopeValidateRequest,
  ScopeValidateResponse,
  SpotPricingEnvelope,
  TriggerEvaluateRequest,
  TriggerEvaluateResponse,
} from "../spot-types";
import { API_BASE_URL, parseErrorResponse, resolveAuthToken } from "./shared";

export async function validateSpotScope(
  request: ScopeValidateRequest,
): Promise<ScopeValidateResponse> {
  const url = API_BASE_URL + "/api/v3/spot/validate-scope/";
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Scope validation failed: ${detail}`);
  }

  return response.json();
}

export async function evaluateSpotTrigger(
  request: TriggerEvaluateRequest,
): Promise<TriggerEvaluateResponse> {
  const url = API_BASE_URL + "/api/v3/spot/evaluate-trigger/";
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Trigger evaluation failed: ${detail}`);
  }

  return response.json();
}

export async function createSpotEnvelope(
  request: CreateSPERequest,
): Promise<SpotPricingEnvelope> {
  const url = API_BASE_URL + "/api/v3/spot/envelopes/";
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Token ${resolveAuthToken()}`,
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    const detail = await parseErrorResponse(response);
    throw new Error(`Failed to create SPE: ${detail}`);
  }

  return response.json();
}
