import { apiGet, apiJson } from "@/lib/api/client";

// Contrats miroir de `apps/api/src/pbm_api/routers/jeu_rendu.py` (lot `j-rendu-carte`, DJ5).
//
// Ce fichier ne sait **pas** choisir un rendu, et c'est volontaire : le choix est fait par le
// serveur, carte par carte et regard par regard (`VueRenduCarte` dans `lib/game/plateau.ts`). Si
// l'écran décidait, le réglage « ne jamais montrer mes photos » ne serait qu'une politesse : l'URL
// de la photo aurait déjà été envoyée à l'adversaire. Ici on ne fait que lire et régler.

/** Les cartes du joueur, telles qu'il les a photographiées. */
export const RENDU_PHOTO = "photo";
/** Les images officielles du catalogue, les mêmes pour tout le monde. */
export const RENDU_OFFICIELLE = "officielle";

/**
 * Mes réglages de rendu, plus ce que le produit impose. `largeur_jeu`/`hauteur_jeu` sont la taille
 * réelle de la variante servie en partie : publiée pour qu'un joueur qui se demande si « sa » carte
 * sera nette puisse lire le chiffre, pas pour que l'écran en déduise quoi que ce soit.
 */
export type ReglagesRendu = {
  rendus_possibles: string[];
  rendu_defaut: string;
  jamais_montrer_mes_photos: boolean;
  largeur_jeu: number;
  hauteur_jeu: number;
};

/** Modification **partielle** : seuls les champs fournis changent côté serveur. */
export type PatchReglagesRendu = Partial<
  Pick<ReglagesRendu, "rendu_defaut" | "jamais_montrer_mes_photos">
>;

/** Une carte du deck qui ne se jouera **pas** avec sa photo, et la raison. */
export type ApercuCarteRendu = {
  card_id: string;
  nom: string;
  origine: string;
  raison: string | null;
};

/**
 * Ce que les cartes d'un deck montreront en jeu. `cartes` ne porte que celles qui se replieront sur
 * l'image officielle alors que le joueur a demandé ses photos : lister les soixante noierait
 * l'information utile. `nb_photos`/`nb_officielles` donnent le compte complet.
 */
export type ApercuDeckRendu = {
  rendu_effectif: string;
  rendu_deck: string | null;
  nb_photos: number;
  nb_officielles: number;
  cartes: ApercuCarteRendu[];
};

/** Mes réglages de rendu (les défauts DJ5 si je n'y ai jamais touché). */
export function getRenduSettings(): Promise<ReglagesRendu> {
  return apiGet<ReglagesRendu>("/jeu/rendu/reglages");
}

/** Modifie mes réglages (partiellement) et rend l'état complet qui en résulte. */
export function updateRenduSettings(patch: PatchReglagesRendu): Promise<ReglagesRendu> {
  return apiJson<ReglagesRendu>("PATCH", "/jeu/rendu/reglages", patch);
}

/**
 * Ce que les cartes de **mon** deck montreront en jeu (le deck d'un autre répond 404).
 *
 * Cet appel a un effet de bord assumé côté serveur : il **prépare** les variantes de jeu
 * manquantes. C'est le moment « à l'avance » du lot — regarder son deck avant de jouer — et c'est
 * ce qui évite de fabriquer des images pendant une partie.
 */
export function getDeckRendu(deckId: string): Promise<ApercuDeckRendu> {
  return apiGet<ApercuDeckRendu>(`/jeu/rendu/decks/${deckId}`);
}

/** Le nom lisible d'un rendu, pour une étiquette de réglage. */
export function libelleRendu(rendu: string): string {
  if (rendu === RENDU_PHOTO) return "Mes cartes, telles que je les ai photographiées";
  if (rendu === RENDU_OFFICIELLE) return "Les images officielles du catalogue";
  return rendu;
}
