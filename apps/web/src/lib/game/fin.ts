// Fin de partie, côté écran : qui a gagné, pourquoi, et ce que ça laisse sur le compte.
//
// Lot `j-partie-fin-ui` (jalon J4). Module **pur** : aucune requête, aucun React, aucune date
// implicite — il transforme ce que le serveur a décidé en mots français. L'interface ne décide de
// rien : le vainqueur et la raison viennent du moteur (`EtatPartie.vainqueur` / `raison_fin`), ce
// fichier ne fait que les nommer.
//
// Deux exigences du lot vivent ici, et elles tirent dans le même sens.
//
// 1. **Chaque raison de fin a son libellé propre.** Il y en a huit — pas sept : l'égalité
//    (`egalite`) est une raison comme les autres, et c'est précisément celle qu'on oublie. Un code
//    sans libellé serait affiché brut au joueur (« plus_de_pokemon ») ; un test de parité côté
//    moteur (`apps/game/tests/test_parite_raisons_fin_front.py`) casse la CI si le moteur en ajoute
//    une sans passer ici.
// 2. **Ne pas humilier le perdant.** Le jeu est celui d'un enfant de onze ans : on dit ce qui s'est
//    passé, jamais ce que ça dit du joueur. Pas de « défaite écrasante », pas de « tu as perdu
//    bêtement ». Chaque raison a donc **trois** phrases — une par issue — plutôt qu'une phrase
//    neutre qu'on afficherait à tout le monde : « tu as pris ta dernière récompense » et « ton
//    adversaire a pris sa dernière récompense » racontent le même fait sans le même goût.
//
// La **désertion** et l'**inactivité** méritent un mot : ce ne sont pas des fins méritées. On le
// dit (« la partie s'est arrêtée faute de joueurs »), on ne la présente pas comme une victoire
// gagnée au jeu.

/** Les trois issues possibles d'une partie finie, du point de vue du joueur qui regarde. */
export type IssueFin = "victoire" | "defaite" | "nulle";

/** Les libellés d'une raison de fin : son nom court, et la phrase qui convient à chaque issue. */
export type LibellesRaison = {
  /** Nom court, pour le journal et les listes (« abandon », « temps écoulé »). */
  court: string;
  /** Ce qu'on dit au gagnant. */
  victoire: string;
  /** Ce qu'on dit au perdant — un fait, jamais un jugement. */
  defaite: string;
  /** Ce qu'on dit quand il n'y a pas de vainqueur. */
  nulle: string;
};

/**
 * Les huit raisons de fin du moteur, chacune avec ses libellés.
 *
 * Miroir **exact** des constantes `RAISON_*` de `pbm_game.journal.modele` et de
 * `RAISON_EGALITE` (`pbm_game.state.modele`). Ne jamais y ajouter de clé sans sa contrepartie
 * moteur, ni en retirer une : le test de parité lit ce registre.
 */
export const RAISONS_FIN: Record<string, LibellesRaison> = {
  derniere_recompense: {
    court: "dernière récompense prise",
    victoire: "Tu as pris ta dernière carte récompense.",
    defaite: "Ton adversaire a pris sa dernière carte récompense.",
    nulle: "Les deux joueurs ont pris leur dernière carte récompense en même temps.",
  },
  plus_de_pokemon: {
    court: "plus de Pokémon en jeu",
    victoire: "Ton adversaire n'avait plus de Pokémon à envoyer au combat.",
    defaite: "Tu n'avais plus de Pokémon à envoyer au combat.",
    nulle: "Plus aucun des deux joueurs n'avait de Pokémon à envoyer au combat.",
  },
  pioche_impossible: {
    court: "pioche impossible",
    victoire: "Ton adversaire n'avait plus de carte à piocher en début de tour.",
    defaite: "Tu n'avais plus de carte à piocher en début de tour.",
    nulle: "Aucun des deux joueurs n'avait plus de carte à piocher.",
  },
  abandon: {
    court: "abandon",
    victoire: "Ton adversaire a préféré arrêter la partie.",
    defaite: "Tu as arrêté la partie.",
    nulle: "La partie s'est arrêtée là.",
  },
  temps_ecoule: {
    court: "temps écoulé",
    victoire: "Le temps de ton adversaire s'est écoulé.",
    defaite: "Ton temps s'est écoulé.",
    nulle: "Le temps s'est écoulé pour les deux joueurs.",
  },
  desertion: {
    court: "désertion",
    victoire: "Ton adversaire n'est pas revenu dans la partie.",
    defaite: "Tu n'es pas revenu dans la partie à temps.",
    nulle: "Plus personne n'était là pour jouer.",
  },
  inactivite: {
    court: "partie inactive",
    victoire: "La partie s'est arrêtée faute de joueurs : elle ne compte pour personne.",
    defaite: "La partie s'est arrêtée faute de joueurs : elle ne compte pour personne.",
    nulle: "La partie s'est arrêtée faute de joueurs : elle ne compte pour personne.",
  },
  egalite: {
    court: "égalité",
    victoire: "Vous avez rempli une condition de victoire en même temps.",
    defaite: "Vous avez rempli une condition de victoire en même temps.",
    nulle: "Vous avez rempli une condition de victoire exactement en même temps.",
  },
};

/** Nom court d'une raison de fin, ou le code brut s'il est inconnu (jamais masqué). */
export function raisonCourte(code: string | null | undefined): string {
  if (!code) return "?";
  return RAISONS_FIN[code]?.court ?? code;
}

/**
 * La phrase qui explique la fin, du point de vue de celui qui regarde.
 *
 * Une raison inconnue (moteur plus récent que l'écran) remonte son code entre parenthèses plutôt
 * que de disparaître : un identifiant technique affiché est laid, une fin sans explication est
 * une panne muette.
 */
export function phraseDeFin(code: string | null | undefined, issue: IssueFin): string {
  if (!code) return "La partie est terminée.";
  const libelles = RAISONS_FIN[code];
  if (!libelles) return `La partie est terminée (${code}).`;
  return libelles[issue];
}

/**
 * L'issue de la partie pour `moiUserId`, depuis le vainqueur décidé par le serveur.
 *
 * `vainqueurUserId` à `null` = pas de vainqueur (égalité R-14.4, ou clôture pour inactivité) :
 * l'issue est « nulle » pour les deux joueurs. On ne compare jamais que des identifiants de
 * **compte** : l'identifiant moteur (`vue.vainqueur`) est un autre espace de noms, et les
 * confondre donnerait une victoire au mauvais joueur.
 */
export function issueDeFin(
  vainqueurUserId: string | null | undefined,
  moiUserId: string | null | undefined,
): IssueFin {
  if (!vainqueurUserId) return "nulle";
  if (!moiUserId) return "nulle";
  return vainqueurUserId === moiUserId ? "victoire" : "defaite";
}

/**
 * Le titre de l'écran de fin — trois mots au plus (contrainte de la police pixel `.pbm-titre`).
 *
 * Volontairement sobre côté défaite : « C'est passé près » dit l'issue sans la commenter.
 */
export function titreDeFin(issue: IssueFin): string {
  if (issue === "victoire") return "Gagné !";
  if (issue === "defaite") return "C'est passé près";
  return "Match nul";
}

/** Un résultat de partie réduit à ce qu'il faut pour tenir une série (miroir de `GameSummary`). */
export type ResultatPartie = {
  status: string;
  vainqueur_user_id: string | null;
  raison_fin: string | null;
  updated_at: string;
  entrainement: boolean;
};

/** Ce que les parties jouées disent du compte : total, victoires, et série de victoires en cours. */
export type BilanCompte = {
  /** Parties terminées qui comptent (hors entraînement). */
  parties: number;
  victoires: number;
  nulles: number;
  /** Victoires consécutives en terminant par la partie la plus récente (0 si la dernière n'en est pas une). */
  serie: number;
};

/**
 * Ce que l'historique du compte dit, calculé depuis la liste de ses parties.
 *
 * Les parties d'**entraînement** sont exclues : DJ7 les fait entrer dans l'historique mais elles
 * « ne comptent pas » — les inclure dans une série gonflerait un chiffre que le joueur fabrique
 * lui-même contre un bot. Les parties **non terminées** sont exclues aussi : une partie en cours
 * n'a pas de résultat.
 *
 * La série est comptée depuis la partie la plus récente vers le passé, et s'arrête à la première
 * qui n'est pas une victoire. Elle vaut donc 0 juste après une défaite — c'est l'intérêt : elle
 * dit « en ce moment », pas « au mieux ».
 *
 * Fonction pure : elle trie une copie (`updated_at` décroissant) et ne touche pas l'entrée.
 */
export function bilanCompte(parties: ResultatPartie[], moiUserId: string): BilanCompte {
  const comptees = parties
    .filter((p) => !p.entrainement && p.status !== "en_cours")
    .slice()
    .sort((a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0));

  let victoires = 0;
  let nulles = 0;
  for (const p of comptees) {
    const issue = issueDeFin(p.vainqueur_user_id, moiUserId);
    if (issue === "victoire") victoires += 1;
    else if (issue === "nulle") nulles += 1;
  }

  let serie = 0;
  for (const p of comptees) {
    if (issueDeFin(p.vainqueur_user_id, moiUserId) !== "victoire") break;
    serie += 1;
  }

  return { parties: comptees.length, victoires, nulles, serie };
}

/**
 * Une durée en secondes, dite en français court (« 7 min 12 s »).
 *
 * `null` → « inconnue » : un journal dont les horodatages sont illisibles ne vaut pas un « 0 s »
 * qui se lirait « partie instantanée ».
 */
export function dureeEnFrancais(secondes: number | null | undefined): string {
  if (secondes === null || secondes === undefined) return "inconnue";
  if (secondes < 60) return `${secondes} s`;
  const minutes = Math.floor(secondes / 60);
  const reste = secondes % 60;
  if (minutes < 60) return reste ? `${minutes} min ${reste} s` : `${minutes} min`;
  const heures = Math.floor(minutes / 60);
  const minutesRestantes = minutes % 60;
  return minutesRestantes ? `${heures} h ${minutesRestantes} min` : `${heures} h`;
}
