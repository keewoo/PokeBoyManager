import type { components } from "@pbm/api-client";

import { apiJson } from "@/lib/api/client";

export { ApiError } from "@/lib/api/client";

export type MessageResponse = components["schemas"]["MessageResponse"];
export type UserResponse = components["schemas"]["UserResponse"];

export function registerAccount(email: string, password: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/register", { email, password });
}

export function verifyEmail(token: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/verify-email", { token });
}

export function login(email: string, password: string): Promise<UserResponse> {
  return apiJson<UserResponse>("POST", "/auth/login", { email, password });
}

export function forgotPassword(email: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/forgot", { email });
}

export function resetPassword(token: string, password: string): Promise<MessageResponse> {
  return apiJson<MessageResponse>("POST", "/auth/reset", { token, password });
}
