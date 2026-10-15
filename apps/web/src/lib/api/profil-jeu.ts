import { apiGet, apiJson } from "@/lib/api/client";

// Contrat miroir de `apps/api/src/pbm_api/routers/profil_jeu.py` (lot `j-profil-jeu`, DJ6).
//
// Le serveur publie son vocabulaire (`mesures_possibles`) et son palier (`palier_parties`) :
// l'écran les affiche, il ne les code pas en dur. Et c'est le serveur qui décide du **rendu** de la
// carte fétiche (photo ou image officielle, DJ5) : si l'écran choisissait, le veto « ne jamais
// montrer mes photos » serait contournable depuis le navigateur.

/** Le rendu d'une carte décidé par le serveur — la forme déjà connue du plateau. */
export type RenduCarte = {
  origine: string;
  url: string;
  url_zoom: string;
  credit: string | null;
  raison: string | null;
  url_repli: string | null;
};

/** La carte fétiche : son identité catalogue, et le rendu que le serveur a arbitré. */
export type CarteFetiche = {
  card_id: string;
  nom: string;
  rendu: RenduCarte;
};

/** Un badge de la vitrine, obtenu ou non. `mesure` dit ce qu'il récompense. */
export type BadgeJoueur = {
  code: string;
  nom: string;
  description: string;
  mesure: string;
  obtenu: boolean;
  obtenu_a: string | null;
  game_id: string | null;
};

/** Ma vitrine de joueur : identité reprise du compte, carte fétiche, badges, décors. */
export type ProfilJeu = {
  pseudo: string | null;
  a_un_avatar: boolean;
  carte_fetiche: CarteFetiche | null;
  /** Faux tant que JF n'a pas allumé les badges (DJ6) : `badges` est alors vide. */
  badges_actifs: boolean;
  badges: BadgeJoueur[];
  mesures_possibles: string[];
  palier_parties: number;
  decors: string[];
  decor_choisi: string | null;
};

/** Ma vitrine de joueur (`GET /jeu/profil`). 404 sans accès au jeu (D11). */
export function getProfilJeu(): Promise<ProfilJeu> {
  return apiGet<ProfilJeu>("/jeu/profil");
}

/**
 * Pose (ou retire, avec `null`) ma carte fétiche, et rend la vitrine qui en résulte.
 *
 * 422 quand la carte n'est pas dans ma collection : le message du serveur est **affichable tel
 * quel**, c'est lui qui explique au joueur ce qui s'est passé.
 */
export function poserCarteFetiche(cardId: string | null): Promise<ProfilJeu> {
  return apiJson<ProfilJeu>("PUT", "/jeu/profil/carte-fetiche", { card_id: cardId });
}

/** Libellé français d'une mesure de badge — pour regrouper la vitrine sans inventer de mots. */
export function libelleMesure(mesure: string): string {
  switch (mesure) {
    case "issue":
      return "Gagner";
    case "exploit":
      return "Exploits";
    case "volume":
      return "Parcours";
    case "construction":
      return "Construction de deck";
    default:
      // Une mesure inconnue du client (serveur plus récent) s'affiche telle quelle plutôt que
      // d'être masquée : un badge sans groupe reste visible, et l'écart se voit.
      return mesure;
  }
}
