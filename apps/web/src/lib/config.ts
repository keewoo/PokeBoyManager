export function getApiBaseUrl(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) {
    return "http://localhost:8000";
  }
  return url.replace(/\/+$/, "");
}

// Doit rester alignée avec `SESSION_COOKIE_NAME` côté `apps/api` (`pbm_api.config.Settings`).
export function getSessionCookieName(): string {
  return process.env.NEXT_PUBLIC_SESSION_COOKIE_NAME || "pbm_session";
}
