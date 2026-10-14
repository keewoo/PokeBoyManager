import { apiGet, apiJson } from "@/lib/api/client";
import type { ReglagesConfort } from "@/lib/game/confort";

// Contrat miroir de `apps/api/src/pbm_api/routers/jeu_confort.py` (lot `j-accessibilite-jeu`).
//
// Le serveur publie son propre vocabulaire (`animations_possibles`, `tailles_possibles`) et le
// facteur du temps rallongé : l'écran les affiche, il ne les code pas en dur. Quand les deux
// divergeraient, c'est le serveur qui a raison — c'est lui qui refuse une valeur inconnue.

/** Mes réglages de confort, plus ce que le produit impose (vocabulaire et facteur de temps). */
export type ConfortServeur = ReglagesConfort & {
  animations_possibles: string[];
  tailles_possibles: string[];
  /** De combien les horloges d'une partie sont multipliées quand le temps rallongé est actif. */
  facteur_temps_rallonge: number;
};

/** Modification **partielle** : seuls les champs fournis changent côté serveur. */
export type PatchConfort = Partial<ReglagesConfort>;

/** Mes réglages de confort (les défauts si je n'y ai jamais touché). 404 sans accès au jeu (D11). */
export function getConfort(): Promise<ConfortServeur> {
  return apiGet<ConfortServeur>("/jeu/confort/reglages");
}

/** Modifie mes réglages (partiellement) et rend l'état complet qui en résulte. */
export function updateConfort(patch: PatchConfort): Promise<ConfortServeur> {
  return apiJson<ConfortServeur>("PATCH", "/jeu/confort/reglages", patch);
}
