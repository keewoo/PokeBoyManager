import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "@/middleware";

function requestFor(path: string, cookie?: string): NextRequest {
  const headers = cookie ? { cookie } : undefined;
  return new NextRequest(new URL(path, "http://localhost:3000"), { headers });
}

describe("middleware — espace jeu", () => {
  it("protège /jeu/decks : sans session, redirection vers /connexion avec next", () => {
    const response = middleware(requestFor("/jeu/decks"));
    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location")!);
    expect(location.pathname).toBe("/connexion");
    expect(location.searchParams.get("next")).toBe("/jeu/decks");
  });

  it("laisse passer /jeu/decks avec un cookie de session", () => {
    const response = middleware(requestFor("/jeu/decks/abc", "pbm_session=xyz"));
    expect(response.status).toBe(200);
    expect(response.headers.get("location")).toBeNull();
  });
});
