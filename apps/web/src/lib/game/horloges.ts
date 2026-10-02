// Horloges d'une partie, côté navigateur (lot `j-timer`).
//
// Le serveur fait autorité : il décompte et renvoie, à chaque événement et à chaque battement, le
// temps restant « vérité serveur » (type `HorlogesServeur`). Le client n'en fait qu'une **estimation
// locale** entre deux messages — jamais une seconde source de vérité. L'estimation retranche
// seulement le temps écoulé **localement depuis la réception** du dernier instantané serveur ; à
// chaque nouveau message, elle se **recale** sur la valeur serveur. C'est ce qui garde l'écran à
// moins de deux secondes de la vérité serveur (critère d'acceptation) : aucun compteur ne court
// librement en accumulant de la dérive — il repart du serveur à chaque coup.
//
// Pur et sans dépendance au navigateur (le temps entre par paramètre) : testable en mémoire.

/** Le temps restant d'un joueur, tel que le serveur le calcule (ou l'estimation locale qui en dérive). */
export type HorlogeJoueur = {
  /** Budget total restant (secondes) — le plafond « temps par joueur ». */
  budget_s: number;
  /** L'horloge courte qui court pour ce joueur : « tour », « decision », ou `null` s'il ne décompte pas. */
  genre: "tour" | "decision" | null;
  /** Restant sur l'horloge courte (secondes), ou `null` si ce joueur ne décompte pas. */
  horloge_s: number | null;
};

/** Le temps restant de la partie à un instant serveur donné (charge `restant` côté API). */
export type HorlogesServeur = {
  /** Instant serveur du calcul (époque en secondes) — repère de la dérive côté client. */
  maintenant: number;
  /** Une pause de déconnexion gèle-t-elle les horloges ? */
  en_pause: boolean;
  /** Identifiant du joueur déconnecté, ou `null`. */
  pause_joueur: string | null;
  /** Secondes de grâce restantes avant la fin de la pause, ou `null` hors pause. */
  pause_restant_s: number | null;
  /** Le temps restant, par identifiant de joueur. */
  joueurs: Record<string, HorlogeJoueur>;
};

/**
 * Estime le temps restant à `maintenantLocalMs` à partir d'un instantané serveur reçu à
 * `recuLocalMs` (horloges du navigateur, en millisecondes).
 *
 * Règles : les horloges de jeu (budget, horloge courte) ne décomptent que pour le joueur qui
 * compte et **seulement hors pause** (une pause les gèle) ; la grâce de pause, elle, s'écoule en
 * temps réel même en pause. On ne borne pas l'horloge courte à 0 (elle peut passer légèrement sous
 * zéro dans la tolérance réseau avant l'expiration côté serveur) ; le budget, lui, reste ≥ 0.
 */
export function estimerHorloges(
  instantane: HorlogesServeur,
  recuLocalMs: number,
  maintenantLocalMs: number,
): HorlogesServeur {
  const ecouleS = Math.max(0, (maintenantLocalMs - recuLocalMs) / 1000);
  const geleJeu = instantane.en_pause;
  const joueurs: Record<string, HorlogeJoueur> = {};
  for (const [jid, info] of Object.entries(instantane.joueurs)) {
    const compteLui = info.genre !== null;
    joueurs[jid] = {
      genre: info.genre,
      budget_s: Math.max(0, info.budget_s - (compteLui && !geleJeu ? ecouleS : 0)),
      horloge_s: info.horloge_s === null ? null : info.horloge_s - (geleJeu ? 0 : ecouleS),
    };
  }
  return {
    maintenant: instantane.maintenant,
    en_pause: instantane.en_pause,
    pause_joueur: instantane.pause_joueur,
    pause_restant_s:
      instantane.pause_restant_s === null
        ? null
        : instantane.pause_restant_s - (geleJeu ? ecouleS : 0),
    joueurs,
  };
}

/**
 * Formate un nombre de secondes en « m:ss » pour l'affichage (jamais négatif à l'écran).
 * Exemple : 90 → « 1:30 », 5 → « 0:05 ». Un restant négatif (tolérance réseau) s'affiche « 0:00 ».
 */
export function formatSecondes(secondes: number): string {
  const total = Math.max(0, Math.round(secondes));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
