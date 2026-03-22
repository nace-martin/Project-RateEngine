import type { User } from "../types";
import { API_BASE_URL, resolveAuthToken } from "./shared";

export async function getMe(): Promise<User> {
  const url = API_BASE_URL + "/api/auth/me/";
  const response = await fetch(url, {
    headers: {
      Authorization: `Token ${resolveAuthToken()}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch user data.");
  }

  return response.json();
}
