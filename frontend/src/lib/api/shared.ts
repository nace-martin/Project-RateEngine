import { API_BASE_URL } from "../config";

export { API_BASE_URL };

export const getToken = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem("authToken");
};

export const resolveAuthToken = (tokenOverride?: string | null): string => {
  const token = tokenOverride ?? getToken();
  if (!token) {
    throw new Error("Authentication token not available. Please log in.");
  }
  return token;
};

export const parseErrorResponse = async (response: Response): Promise<string> => {
  try {
    const data = await response.json();
    if (typeof data === "string") {
      return data;
    }
    if (data && typeof data === "object") {
      if ("detail" in data && typeof data.detail === "string") {
        return data.detail;
      }
      return JSON.stringify(data);
    }
  } catch {
    // ignore parse errors
  }
  return response.statusText || "Unknown error";
};
