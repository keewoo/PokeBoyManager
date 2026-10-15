import { apiGet } from "@/lib/api/client";

// Contrat miroir de `apps/api/src/pbm_api/routers/stats_joueur.py` (lot `j-stats-joueur`).
//
// Deux routes en lecture, rien en écriture : rien n'est stocké côté serveur, tout est recalculé à
// chaque appel depuis l'historique des parties. Il n'y a donc pas de « remise à zéro de mes
// statistiques » à câbler ici — et aucun agrégat ne peut rester faux après un correctif.
//
// **Le seuil de significativité vient du serveur**, il n'est pas recodé ici : `Taux.significatif`
// est calculé à côté du pourcentage par la fonction qui compte, et `seuil_significativite` est
// rendu avec les chiffres pour que l'écran puisse écrire la règle sans la connaître. C'est la
// parade au risque du lot : un écran ne peut pas afficher un taux sans avoir sous la main
// l'information qu'il ne veut rien dire.

/** Un bilan victoires/défaites/égalités, et ce qu'il vaut. */
export type Taux = {
  parties: number;
  victoires: number;
  defaites: number;
  egalites: number;
  /** Taux de victoire en pourcentage entier, `null` sans aucune partie (jamais 0 par défaut). */
  pourcentage: number | null;
  /** Faux en dessous de `seuil_significativite` parties : le taux est affiché en sourdine. */
  significatif: boolean;
  /** Combien de parties il reste à jouer pour que ce taux veuille dire quelque chose. */
  parties_manquantes: number;
};

/** Les six compteurs du récapitulatif, cumulés, et deux moyennes par partie. */
export type Chiffres = {
  parties: number;
  degats_infliges: number;
  kos_infliges: number;
  recompenses_prises: number;
  cartes_jouees: number;
  energies_attachees: number;
  coups_joues: number;
  degats_par_partie: number | null;
  coups_par_partie: number | null;
};

/** Mon bilan face à un adversaire. `user_id` est `null` pour la ligne du bot d'entraînement. */
export type StatsAdversaire = {
  user_id: string | null;
  pseudo: string | null;
  bot: boolean;
  taux: Taux;
  derniere_partie_a: string | null;
};

/** Ce qu'un deck a produit, et contre qui. `deck_id` nul = deck supprimé depuis. */
export type StatsDeck = {
  deck_id: string | null;
  deck_nom: string | null;
  taux: Taux;
  chiffres: Chiffres;
  duree_moyenne_s: number | null;
  derniere_partie_a: string | null;
  adversaires: StatsAdversaire[];
};

/** Les totaux d'un compte, recalculés à la lecture (jamais un cache). */
export type Totaux = {
  taux: Taux;
  serie_en_cours: number;
  meilleure_serie: number;
  temps_jeu_s: number;
  parties_entrainement: number;
  temps_jeu_entrainement_s: number;
  premiere_partie_a: string | null;
  derniere_partie_a: string | null;
};

/** Tout ce que la page affiche au-dessus de la liste. */
export type StatistiquesJoueur = {
  /** Nombre de parties en dessous duquel un taux est marqué non significatif (le serveur décide). */
  seuil_significativite: number;
  totaux: Totaux;
  chiffres: Chiffres;
  par_deck: StatsDeck[];
  par_adversaire: StatsAdversaire[];
};

/** Une ligne d'historique : la partie, ce qu'elle a donné, et si son replay existe encore. */
export type PartieJouee = {
  game_id: string;
  finie_a: string;
  resultat: "victoire" | "defaite" | "egalite";
  /** Code du moteur (`abandon`, `temps_ecoule`…) — traduit par `raisonCourte` de `lib/game/fin`. */
  raison_fin: string | null;
  /** Faux pour une partie d'entraînement ou expirée : elle est listée mais n'entre dans aucun taux. */
  comptabilisee: boolean;
  entrainement: boolean;
  deck_id: string | null;
  deck_nom: string | null;
  adversaire_user_id: string | null;
  adversaire_pseudo: string | null;
  adversaire_bot: boolean;
  duree_s: number | null;
  /** Faux après la purge de la partie : aucun lien de replay n'est alors proposé. */
  replay_disponible: boolean;
};

/** Une page d'historique et son total, pour que l'écran sache ce qu'il n'affiche pas. */
export type HistoriqueParties = {
  total: number;
  limite: number;
  offset: number;
  parties: PartieJouee[];
};

/** Les filtres de l'historique. `entrainement` absent = les deux genres de parties. */
export type FiltresParties = {
  resultat?: string;
  deck_id?: string;
  adversaire_user_id?: string;
  entrainement?: boolean;
  limite?: number;
  offset?: number;
};

function query(filtres: FiltresParties): string {
  const params = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(filtres)) {
    if (valeur !== undefined && valeur !== "") params.set(cle, String(valeur));
  }
  const rendu = params.toString();
  return rendu ? `?${rendu}` : "";
}

/** Mes parties closes, la plus récente d'abord. 404 sans accès au jeu (D11). */
export function listMesParties(filtres: FiltresParties = {}): Promise<HistoriqueParties> {
  return apiGet<HistoriqueParties>(`/jeu/mes-parties${query(filtres)}`);
}

/**
 * Mes agrégats, calculés sur **tout** mon historique (jamais sur la page affichée).
 *
 * `deck_id` restreint le calcul à un deck : c'est ce que la fiche de deck appelle, pour obtenir
 * exactement le chiffre que porte la ligne de ce deck dans le tableau général.
 */
export function getMesStatistiques(
  filtres: Pick<FiltresParties, "deck_id" | "adversaire_user_id" | "entrainement"> = {}
): Promise<StatistiquesJoueur> {
  return apiGet<StatistiquesJoueur>(`/jeu/mes-statistiques${query(filtres)}`);
}

/** Le taux de victoire en toutes lettres, ou un tiret s'il n'y a rien à dire. */
export function libelleTaux(taux: Taux): string {
  return taux.pourcentage === null ? "—" : `${taux.pourcentage} %`;
}

/**
 * La phrase qui dit pourquoi un taux ne veut rien dire encore, ou `null` s'il est significatif.
 *
 * Écrite ici (et pas dans chaque écran) pour que la page, la fiche de deck et tout futur appelant
 * disent la même chose — et surtout, la disent.
 */
export function phraseNonSignificatif(taux: Taux): string | null {
  if (taux.significatif) return null;
  if (taux.parties === 0) return "Aucune partie jouée.";
  const reste = taux.parties_manquantes;
  return `Sur ${taux.parties} partie${taux.parties > 1 ? "s" : ""} seulement — encore ${reste} pour que ce taux veuille dire quelque chose.`;
}

/** Une durée en secondes, en heures et minutes lisibles (`null` → tiret). */
export function libelleDuree(secondes: number | null): string {
  if (secondes === null || secondes <= 0) return "—";
  const heures = Math.floor(secondes / 3600);
  const minutes = Math.round((secondes % 3600) / 60);
  if (heures === 0) return `${minutes} min`;
  return minutes === 0 ? `${heures} h` : `${heures} h ${minutes} min`;
}
