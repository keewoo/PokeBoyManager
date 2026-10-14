/**
 * Navigation d'un replay — logique **pure**, sans React ni réseau (lot `j-replay`).
 *
 * Le serveur sert les rangs d'une partie finie, chacun avec l'état projeté à ce point
 * (`ReplayPage`). Tout le reste — avancer, reculer, se placer, jouer en continu, régler la vitesse,
 * reconstruire le fil du journal jusqu'au rang courant — est **local** : c'est ce qui rend la
 * navigation immédiate, et c'est ce que le lot demande (« rejouer le journal localement »).
 *
 * Deux garde-fous portés ici plutôt que dans l'écran :
 *
 * - **on ne se place jamais hors de ce qu'on a** : {@link borner} ramène un rang dans
 *   `[0, dernierCharge]`. Un écran qui laisserait l'index filer au-delà afficherait du vide en
 *   prétendant que la partie s'arrête là ;
 * - **une page partielle se dit** : {@link estComplet} et {@link rangsManquants} donnent de quoi
 *   l'écrire à l'écran. Le serveur ne tronque pas en silence, l'interface non plus.
 *
 * Rien ici ne rejoue une règle : les états sont **déjà** calculés et vérifiés par le serveur (et
 * leurs empreintes comparées au journal). Ce module ne fait que choisir lequel montrer.
 */

import type { ReplayEtape, ReplayPage } from "@/lib/api/games";
import type { CoupJournal } from "@/lib/game/journal";

/** Les vitesses de lecture proposées, en multiples du pas de base. */
export const VITESSES = [0.5, 1, 2, 4] as const;

/** Durée d'un pas de lecture à la vitesse ×1, en millisecondes. */
export const PAS_MS = 1200;

/**
 * Le délai entre deux rangs pour une vitesse donnée. Une vitesse nulle ou négative est refusée
 * plutôt que repliée sur un défaut : elle signifierait « avance d'un rang tous les ∞ » — un écran
 * figé sans que personne sache pourquoi.
 */
export function delaiMs(vitesse: number): number {
  if (!(vitesse > 0)) {
    throw new Error(`Vitesse de replay invalide : ${vitesse} (attendu > 0).`);
  }
  return Math.round(PAS_MS / vitesse);
}

/**
 * Fusionne une page reçue dans les rangs déjà connus : dédupliqués par `rang`, remis dans l'ordre.
 *
 * Les pages arrivent dans l'ordre, mais une page redemandée (reprise après une erreur réseau) peut
 * recouvrir des rangs déjà là — on la laisse alors **remplacer** l'existant plutôt que d'empiler un
 * doublon, comme le plateau le fait pour les coups diffusés.
 */
export function fusionnerRangs(connus: ReplayEtape[], page: ReplayEtape[]): ReplayEtape[] {
  const parRang = new Map<number, ReplayEtape>();
  for (const etape of connus) parRang.set(etape.rang, etape);
  for (const etape of page) parRang.set(etape.rang, etape);
  return [...parRang.values()].sort((a, b) => a.rang - b.rang);
}

/** Le dernier rang réellement chargé, ou `-1` quand on n'a encore rien. */
export function dernierRangCharge(rangs: ReplayEtape[]): number {
  return rangs.at(-1)?.rang ?? -1;
}

/**
 * Ramène `rang` dans ce qui est chargé : `[0, dernierRangCharge]`. Sans aucun rang chargé, rend 0
 * (il n'y a rien à montrer, mais aucun index négatif ne circule).
 */
export function borner(rang: number, rangs: ReplayEtape[]): number {
  const dernier = dernierRangCharge(rangs);
  if (dernier < 0) return 0;
  if (!Number.isFinite(rang)) return 0;
  return Math.min(Math.max(Math.trunc(rang), 0), dernier);
}

/** Le rang demandé est-il déjà chargé ? (sert à savoir s'il faut aller chercher une page). */
export function estCharge(rang: number, rangs: ReplayEtape[]): boolean {
  return rangs.some((e) => e.rang === rang);
}

/** Tous les rangs de la partie sont-ils chargés ? (`total` coups = `total + 1` rangs). */
export function estComplet(rangs: ReplayEtape[], total: number): boolean {
  return dernierRangCharge(rangs) >= total;
}

/** Combien de rangs restent à charger — ce que l'écran annonce plutôt que de le taire. */
export function rangsManquants(rangs: ReplayEtape[], total: number): number {
  return Math.max(0, total - dernierRangCharge(rangs));
}

/** Le rang chargé dont l'indice est `rang`, ou `null` s'il n'est pas (encore) là. */
export function rangA(rangs: ReplayEtape[], rang: number): ReplayEtape | null {
  return rangs.find((e) => e.rang === rang) ?? null;
}

/**
 * Le fil du journal **jusqu'au rang courant inclus**, prêt pour `construireJournal`.
 *
 * Un replay n'affiche pas d'un coup le journal entier : à un rang donné, on n'a vu que les coups
 * joués jusque-là. On ne garde donc que les rangs `1..rang` (le rang 0 ne porte aucun coup), et on
 * prend les événements **du destinataire demandé** — c'est la même suite que celle que ce joueur a
 * reçue en direct, donc le fil est identique à celui qu'il avait sous les yeux.
 */
export function coupsJusqua(
  rangs: ReplayEtape[],
  rang: number,
  destinataire: string,
): CoupJournal[] {
  return rangs
    .filter((e) => e.rang > 0 && e.rang <= rang && e.coup !== null)
    .map((e) => ({
      numero: e.coup!.numero,
      evenements: e.evenements[destinataire] ?? [],
    }));
}

/**
 * Les destinataires servis par une page, dans l'ordre des sièges.
 *
 * En `vue=moi` il n'y en a qu'un ; en `vue=complete` il y en a deux, et l'écran laisse alors
 * **choisir par quels yeux** regarder. On lit l'ordre sur les sièges (pas sur les clés de `vues`,
 * dont l'ordre n'est pas garanti) pour que « joueur 1 / joueur 2 » ne s'inverse pas d'un
 * chargement à l'autre.
 */
export function destinatairesDe(page: Pick<ReplayPage, "joueurs" | "etapes">): string[] {
  const servis = new Set(
    page.etapes.flatMap((e) => Object.keys(e.vues)),
  );
  return page.joueurs.map((j) => j.joueur_id).filter((jid) => servis.has(jid));
}

/** Le pseudo à afficher pour un destinataire, ou un repli lisible (jamais un identifiant nu). */
export function nomDu(page: Pick<ReplayPage, "joueurs">, joueurId: string): string {
  const siege = page.joueurs.find((j) => j.joueur_id === joueurId);
  if (!siege) return "Joueur inconnu";
  if (siege.pseudo) return siege.pseudo;
  // Un siège tenu par le bot d'entraînement n'a pas de pseudo utile à montrer.
  return siege.bot_niveau ? `Bot (${siege.bot_niveau})` : `Joueur ${siege.seat + 1}`;
}
