import type { components } from "@pbm/api-client";

import { getApiBaseUrl } from "@/lib/config";

export type MessageResponse = components["schemas"]["MessageResponse"];
export type UserResponse = components["schemas"]["UserResponse"];

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "Une erreur est survenue. Réessaie dans un instant.";
    throw new ApiError(response.status, message);
  }

  return payload as T;
}

export function registerAccount(email: string, password: string): Promise<MessageResponse> {
  return postJson<MessageResponse>("/auth/register", { email, password });
}

export function verifyEmail(token: string): Promise<MessageResponse> {
  return postJson<MessageResponse>("/auth/verify-email", { token });
}

export function login(email: string, password: string): Promise<UserResponse> {
  return postJson<UserResponse>("/auth/login", { email, password });
}

export function forgotPassword(email: string): Promise<MessageResponse> {
  return postJson<MessageResponse>("/auth/forgot", { email });
}

export function resetPassword(token: string, password: string): Promise<MessageResponse> {
  return postJson<MessageResponse>("/auth/reset", { token, password });
}
