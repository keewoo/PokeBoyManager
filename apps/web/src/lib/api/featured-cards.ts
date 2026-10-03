import { getServerApiBaseUrl } from "@/lib/config";

/** Carte mise en avant sur l'accueil visiteur : identité minimale, sans donnée de collection. */
export type FeaturedCard = {
  id: string;
  name: string;
  number: string;
  set_name: string;
};

// Appel serveur (mission `pbm-front-accueil`, point 1 — accueil visiteur) : `GET /cards/featured`
// est public (pas de session), donc jamais `apiGet` de `lib/api/client.ts` (pensé pour le
// navigateur — cookies de session, origine relative résolue contre `document`). Repli sur une
// liste vide en cas d'échec (jamais une accueil cassé pour un aléa réseau), mais toujours
// journalisé — jamais un échec totalement silencieux.
/**
 * Cartes en vedette de l'accueil (`GET /cards/featured`, route publique) — appel **côté serveur**
 * (Next.js, `getServerApiBaseUrl` + cache ISR 1 h), jamais le client navigateur. En cas d'échec,
 * renvoie une liste vide pour ne pas casser l'accueil, mais le journalise (pas de repli muet).
 */
export async function getFeaturedCards(): Promise<FeaturedCard[]> {
  const base = getServerApiBaseUrl();
  if (!base) return [];

  try {
    const response = await fetch(`${base}/cards/featured`, { next: { revalidate: 3600 } });
    if (!response.ok) {
      console.error(`[featured-cards] ${response.status} ${response.statusText}`);
      return [];
    }
    return (await response.json()) as FeaturedCard[];
  } catch (error) {
    console.error("[featured-cards] l'appel à /cards/featured a échoué", error);
    return [];
  }
}
