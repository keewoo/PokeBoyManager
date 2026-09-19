import { NextResponse, type NextRequest } from "next/server";

import { getSessionCookieName } from "@/lib/config";

export const config = {
  matcher: ["/collection/:path*", "/ajouter/:path*", "/carte/:path*", "/profil/:path*"],
};

export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(getSessionCookieName());
  if (hasSession) {
    return NextResponse.next();
  }

  // Présence du cookie seulement : une session expirée ou révoquée est encore rejetée par
  // l'API (401), qui reste la seule source de vérité. Cette garde évite juste d'afficher
  // une page privée vide à un visiteur qui n'a manifestement pas de session.
  const loginUrl = new URL("/connexion", request.url);
  loginUrl.searchParams.set("next", `${request.nextUrl.pathname}${request.nextUrl.search}`);
  return NextResponse.redirect(loginUrl);
}
