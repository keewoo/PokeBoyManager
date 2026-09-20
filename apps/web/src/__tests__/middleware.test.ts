import { NextRequest } from "next/server";
import { afterEach, describe, expect, it } from "vitest";

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

  // Lot `pbm-front-accueil` : sans `NEXT_PUBLIC_API_URL` (absente en dev sans `.env`, ou build
  // mal configuré), `getApiBaseUrl()` renvoie désormais `/api` (relatif) plutôt que
  // "http://localhost:8000" en dur — une origine relative résout contre 'self', déjà présent :
  // rien à ajouter à `connect-src`/`img-src`, jamais "localhost" dans la CSP non plus.
  describe("connect-src et img-src sans NEXT_PUBLIC_API_URL", () => {
    const ORIGINAL = process.env.NEXT_PUBLIC_API_URL;

    afterEach(() => {
      if (ORIGINAL === undefined) delete process.env.NEXT_PUBLIC_API_URL;
      else process.env.NEXT_PUBLIC_API_URL = ORIGINAL;
    });

    it("n'ajoute aucune origine à connect-src/img-src (l'API relative /api résout contre 'self')", () => {
      delete process.env.NEXT_PUBLIC_API_URL;

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("connect-src 'self';");
      expect(csp).toContain("img-src 'self' data:;");
      expect(csp).not.toContain("localhost");
    });

    it("ajoute l'origine absolue configurée quand NEXT_PUBLIC_API_URL est définie", () => {
      process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.acx-connect.com/api";

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("connect-src 'self' https://pokeboy.acx-connect.com;");
      expect(csp).toContain("img-src 'self' data: https://pokeboy.acx-connect.com;");
    });
  });

  // Lot `v5-e2e` : sans `NEXT_PUBLIC_UPLOAD_ORIGIN` dans `connect-src`, le `PUT` présigné direct
  // du navigateur vers le stockage objet (`STORAGE_BACKEND=s3`) est bloqué par la CSP et tout
  // envoi de photo échoue — trouvé en faisant réellement transiter un fichier par le navigateur
  // (`apps/web/e2e/parcours-complet.spec.ts`), jamais exercé avant par les e2e précédentes.
  describe("connect-src et l'origine du stockage objet", () => {
    const ORIGINAL_API = process.env.NEXT_PUBLIC_API_URL;
    const ORIGINAL_UPLOAD = process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;

    afterEach(() => {
      if (ORIGINAL_API === undefined) delete process.env.NEXT_PUBLIC_API_URL;
      else process.env.NEXT_PUBLIC_API_URL = ORIGINAL_API;
      if (ORIGINAL_UPLOAD === undefined) delete process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;
      else process.env.NEXT_PUBLIC_UPLOAD_ORIGIN = ORIGINAL_UPLOAD;
    });

    it("ajoute l'origine du stockage objet quand NEXT_PUBLIC_UPLOAD_ORIGIN est définie (STORAGE_BACKEND=s3)", () => {
      process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
      process.env.NEXT_PUBLIC_UPLOAD_ORIGIN = "http://localhost:59000";

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("connect-src 'self' http://localhost:8000 http://localhost:59000");
    });

    it("n'ajoute rien à connect-src sans NEXT_PUBLIC_UPLOAD_ORIGIN (STORAGE_BACKEND=local)", () => {
      process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
      delete process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("connect-src 'self' http://localhost:8000;");
    });
  });
});
