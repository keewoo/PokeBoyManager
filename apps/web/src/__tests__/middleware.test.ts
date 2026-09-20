import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "@/middleware";

function requestFor(path: string, cookie?: string): NextRequest {
  const headers = cookie ? { cookie } : undefined;
  return new NextRequest(new URL(path, "http://localhost:3000"), { headers });
}

describe("middleware", () => {
  it("redirige vers /connexion avec ?next=... quand la page privée est visitée sans session", () => {
    const response = middleware(requestFor("/collection"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location")!);
    expect(location.pathname).toBe("/connexion");
    expect(location.searchParams.get("next")).toBe("/collection");
  });

  it("conserve la query string d'origine dans `next`", () => {
    const response = middleware(requestFor("/carte/dracaufeu-ex-xy121?onglet=histoire"));

    const location = new URL(response.headers.get("location")!);
    expect(location.searchParams.get("next")).toBe("/carte/dracaufeu-ex-xy121?onglet=histoire");
  });

  it("laisse passer une page privée quand le cookie de session est présent", () => {
    const response = middleware(requestFor("/profil", "pbm_session=abc123"));

    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });

  it("pose des en-têtes de sécurité même sur une page publique", () => {
    const response = middleware(requestFor("/"));

    expect(response.headers.get("X-Frame-Options")).toBe("DENY");
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(response.headers.get("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
    const csp = response.headers.get("Content-Security-Policy");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("script-src 'self' 'nonce-");
  });

  it("pose aussi les en-têtes de sécurité sur la redirection vers /connexion", () => {
    const response = middleware(requestFor("/collection"));

    expect(response.headers.get("X-Frame-Options")).toBe("DENY");
    expect(response.headers.get("Content-Security-Policy")).toContain("default-src 'self'");
  });

  it("utilise un nonce différent à chaque requête", () => {
    const first = middleware(requestFor("/"));
    const second = middleware(requestFor("/"));

    const nonceOf = (response: ReturnType<typeof middleware>) =>
      response.headers.get("Content-Security-Policy")?.match(/'nonce-([^']+)'/)?.[1];

    expect(nonceOf(first)).toBeTruthy();
    expect(nonceOf(first)).not.toBe(nonceOf(second));
  });
});
