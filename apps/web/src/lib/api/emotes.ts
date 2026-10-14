import { apiGet, apiJson } from "@/lib/api/client";

// Contrats miroir de `apps/api/src/pbm_api/routers/jeu_emotes.py` (lot `j-echanges-emotes`, DJ10).
//
// Ce fichier ne sait **pas** envoyer une emote, et c'est volontaire : l'envoi passe par le canal
// temps réel (`CanalPartie.envoyerEmote`), pas par HTTP. Une route d'envoi voudrait dire une file
// d'attente, donc un stockage — et le lot exige que rien d'une emote ne survive à la partie. Ici on
// ne fait que lire le catalogue de référence et régler l'interrupteur.

/** Mon réglage d'emotes. `recevoir_emotes` à faux coupe la réception **et** l'envoi. */
export type ReglagesEmotes = {
  recevoir_emotes: boolean;
};

/** Le catalogue de référence du serveur, et le débit qu'il applique. */
export type CatalogueEmotes = {
  emotes: { code: string; phrase: string; pictogramme: string }[];
  max_par_fenetre: number;
  fenetre_secondes: number;
  intervalle_min_secondes: number;
};

/** Mon réglage d'emotes (les défauts DJ10 si je n'y ai jamais touché). */
export function getReglagesEmotes(): Promise<ReglagesEmotes> {
  return apiGet<ReglagesEmotes>("/jeu/emotes/reglages");
}

/**
 * Coupe ou rétablit mes emotes. L'effet est immédiat côté serveur (la diffusion relit ce réglage à
 * chaque emote) et mémorisé (la ligne persiste, les parties suivantes la suivent).
 */
export function setReglagesEmotes(
  patch: Partial<ReglagesEmotes>,
): Promise<ReglagesEmotes> {
  return apiJson<ReglagesEmotes>("PATCH", "/jeu/emotes/reglages", patch);
}

/** Le catalogue tel que le serveur l'accepte — la référence, quand on veut la vérifier. */
export function getCatalogueEmotes(): Promise<CatalogueEmotes> {
  return apiGet<CatalogueEmotes>("/jeu/emotes/catalogue");
}
