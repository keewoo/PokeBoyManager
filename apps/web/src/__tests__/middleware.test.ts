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

  // Défaut constaté en PROD le 11/11/2026 : derrière Caddy, `request.url` porte le nom d'écoute du
  // serveur Next (`https://localhost:3100/jeu`), et la redirection partait vers localhost.
  describe("redirection derrière le proxy : l'origine publique, jamais celle du serveur Next", () => {
    function behindProxy(path: string, headers: Record<string, string>): NextRequest {
      return new NextRequest(new URL(path, "https://localhost:3100"), { headers });
    }

    it("prend l'hôte de X-Forwarded-Host (posé par Caddy)", () => {
      const response = middleware(behindProxy("/jeu", { "x-forwarded-host": "pokeboy.lol" }));

      expect(response.status).toBe(307);
      expect(response.headers.get("location")).toBe("https://pokeboy.lol/connexion?next=%2Fjeu");
    });

    it("prend l'hôte de Host quand X-Forwarded-Host manque", () => {
      const response = middleware(behindProxy("/collection", { host: "pokeboy.lol" }));

      expect(response.headers.get("location")).toBe("https://pokeboy.lol/connexion?next=%2Fcollection");
    });

    it("ne garde que le premier hôte d'une liste X-Forwarded-Host", () => {
      const response = middleware(behindProxy("/jeu", { "x-forwarded-host": "pokeboy.lol, autre.example" }));

      expect(new URL(response.headers.get("location")!).host).toBe("pokeboy.lol");
    });

    it("ignore un hôte mal formé et retombe sur celui de la requête", () => {
      const response = middleware(behindProxy("/jeu", { "x-forwarded-host": "evil.example/@x" }));

      expect(new URL(response.headers.get("location")!).host).toBe("localhost:3100");
    });

    // Revue du 11/11/2026 : ces hôtes passent le motif mais `new URL` les refuse ; la requête
    // finissait en erreur 500 au lieu de passer au candidat suivant.
    it.each(["pokeboy.lol:99999", "1.2.3.999", "[1.2.3.4]", "[:::]"])(
      "écarte %s, que l'analyseur d'URL refuse, et passe à Host",
      (forwarded) => {
        const response = middleware(behindProxy("/jeu", { "x-forwarded-host": forwarded, host: "pokeboy.lol" }));

        expect(response.status).toBe(307);
        expect(response.headers.get("location")).toBe("https://pokeboy.lol/connexion?next=%2Fjeu");
      }
    );

    it("retombe sur l'origine de la requête quand aucun candidat n'est utilisable", () => {
      const response = middleware(behindProxy("/jeu", { "x-forwarded-host": "1.2.3.999", host: "pokeboy.lol:99999" }));

      expect(response.status).toBe(307);
      expect(new URL(response.headers.get("location")!).host).toBe("localhost:3100");
    });

    it("garde un hôte IPv6 entre crochets et son port", () => {
      const response = middleware(behindProxy("/jeu", { host: "[::1]:3100" }));

      expect(new URL(response.headers.get("location")!).host).toBe("[::1]:3100");
    });

    describe("origine fixée par NEXT_PUBLIC_SITE_URL (build de PROD)", () => {
      const ORIGINAL = process.env.NEXT_PUBLIC_SITE_URL;

      afterEach(() => {
        if (ORIGINAL === undefined) delete process.env.NEXT_PUBLIC_SITE_URL;
        else process.env.NEXT_PUBLIC_SITE_URL = ORIGINAL;
      });

      it("redirige vers l'origine configurée, quels que soient X-Forwarded-Host et Host", () => {
        process.env.NEXT_PUBLIC_SITE_URL = "https://pokeboy.lol";

        const response = middleware(
          behindProxy("/collection", { "x-forwarded-host": "evil.example", host: "autre.example" })
        );

        expect(response.headers.get("location")).toBe("https://pokeboy.lol/connexion?next=%2Fcollection");
      });

      it("ignore une valeur illisible ou hors http(s) et revient aux en-têtes", () => {
        for (const value of ["pas une url", "ftp://pokeboy.lol"]) {
          process.env.NEXT_PUBLIC_SITE_URL = value;

          const response = middleware(behindProxy("/jeu", { "x-forwarded-host": "pokeboy.lol" }));

          expect(response.headers.get("location")).toBe("https://pokeboy.lol/connexion?next=%2Fjeu");
        }
      });
    });
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
      process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.lol/api";

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("connect-src 'self' https://pokeboy.lol wss://pokeboy.lol;");
      expect(csp).toContain("img-src 'self' data: https://pokeboy.lol;");
    });
  });

  // Lot `j-e2e-deux-navigateurs` : le canal temps réel du jeu ouvre un WebSocket vers l'API. Une
  // source `http://hôte` de `connect-src` ne couvre PAS `ws://hôte` dans Chromium — sans l'origine
  // `ws:`/`wss:` nommée, le navigateur refuse le socket, le canal replie en interrogation
  // périodique, et la partie tourne en mode dégradé **en permanence sans que rien n'échoue**.
  // Trouvé en ouvrant une vraie partie dans un vrai navigateur (deux contextes Playwright).
  describe("connect-src et le WebSocket du jeu", () => {
    const ORIGINAL = process.env.NEXT_PUBLIC_API_URL;

    afterEach(() => {
      if (ORIGINAL === undefined) delete process.env.NEXT_PUBLIC_API_URL;
      else process.env.NEXT_PUBLIC_API_URL = ORIGINAL;
    });

    it("nomme l'origine ws:// quand l'API est sur une autre origine en http (dev, CI, e2e)", () => {
      process.env.NEXT_PUBLIC_API_URL = "http://localhost:8100";

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("ws://localhost:8100");
    });

    it("nomme l'origine wss:// quand l'API est en https (UAT/PROD)", () => {
      process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.lol/api";

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("wss://pokeboy.lol");
      expect(csp, "jamais de ws:// en clair quand l'API est en https").not.toContain(
        "ws://pokeboy.lol",
      );
    });

    it("n'ajoute aucune origine ws quand l'API est relative (le socket est alors same-origin, couvert par 'self')", () => {
      delete process.env.NEXT_PUBLIC_API_URL;

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      expect(csp).toContain("connect-src 'self';");
      expect(csp).not.toContain("ws:");
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

      expect(csp).toContain(
        "connect-src 'self' http://localhost:8000 ws://localhost:8000 http://localhost:59000",
      );
    });

    it("n'ajoute rien à connect-src sans NEXT_PUBLIC_UPLOAD_ORIGIN (STORAGE_BACKEND=local)", () => {
      process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000";
      delete process.env.NEXT_PUBLIC_UPLOAD_ORIGIN;

      const csp = middleware(requestFor("/")).headers.get("Content-Security-Policy");

      // L'origine `ws://` du canal de jeu reste là (elle ne dépend pas du stockage objet) ; c'est
      // bien l'origine d'envoi qui est absente.
      expect(csp).toContain("connect-src 'self' http://localhost:8000 ws://localhost:8000;");
    });
  });
});
