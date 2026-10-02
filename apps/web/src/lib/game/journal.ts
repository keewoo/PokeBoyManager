/**
 * Journal de partie — traduction **pure** des événements du moteur en phrases françaises
 * (lot `j-plateau-journal`).
 *
 * Le moteur (`pbm_game`) produit, pour chaque coup, une suite d'événements `{type, donnees}` que le
 * serveur **projette** pour chaque joueur (point de sortie unique `pbm_game.sortie`) et diffuse au
 * client (`Coup = {numero, evenements}`, voir `realtime.ts`). Ce module traduit cette suite en un
 * **fil lisible** : « Tu pioches 2 cartes », « Poison sur ton Actif : 10 dégâts », « Dégâts : 120 ».
 *
 * Règles qui gouvernent ce module :
 *
 * - **aucun `event_type` brut affiché** : chaque type d'événement que le serveur peut diffuser a son
 *   traducteur dans {@link TRADUCTEURS}. Un type sans traducteur retombe sur une ligne explicitement
 *   marquée `traduit: false` (jamais masquée en silence) — et un test de parité
 *   (`apps/game/tests/test_parite_journal_front.py`) **échoue en CI** si un événement projetable du
 *   moteur n'a pas sa traduction ici ;
 * - **l'interface ne décide de rien** : on ne rejoue aucune règle, on ne devine aucun camp. Le camp
 *   d'un coup se lit sur `donnees.joueur` (comparé au destinataire `pour`) ; pour les rares
 *   événements qui n'en portent pas (les dégâts portent la *cible*, pas l'auteur), on retombe sur
 *   l'auteur du coup déduit de ses événements voisins, jamais sur une supposition ;
 * - **pur** : aucun React, aucune E/S, aucune dépendance au DOM. Testable sans navigateur.
 *
 * L'image réelle des cartes et leurs noms complets restent le lot aval `j-rendu-carte` : ici on
 * nomme ce que l'événement porte (une `ref`, un nom d'évolution) et on **relie** chaque ligne à la
 * carte du plateau par la surbrillance au survol (`surligne`), sans fabriquer d'image qu'on n'a pas
 * (D9).
 */

import { ETATS } from "@/lib/game/indicateurs";

/** Un événement diffusé par le serveur : son type et ses données (valeurs JSON natives). */
export type EvenementJournal = { type?: string; donnees?: Record<string, unknown> };

/** Un coup diffusé : son numéro de séquence et ses événements déjà projetés par le serveur. */
export type CoupJournal = { numero: number; evenements: unknown[] };

/**
 * La catégorie d'une ligne, pour les filtres du fil :
 * - `"moi"` / `"adversaire"` : un coup joué par un joueur (déduit de `donnees.joueur`) ;
 * - `"auto"` : un **effet automatique** du jeu (Checkup, expiration d'un effet, changement de phase,
 *   K.O. hors attaque, fin de partie) — ce qu'on ne comprend pas autrement.
 */
export type CategorieLigne = "moi" | "adversaire" | "auto";

/** Une ligne du fil, prête à afficher : self-contenue, sans dépendance à la vue courante. */
export type LigneJournal = {
  /** Clé stable (numéro de coup + rang de l'événement) pour le rendu React. */
  cle: string;
  /** Numéro du coup d'où vient l'événement. */
  numero: number;
  /** Type brut de l'événement (pour le débogage et les tests, jamais le seul affichage). */
  type: string;
  /** La phrase française. */
  texte: string;
  /** `false` si aucun traducteur n'a reconnu le type (l'identifiant brut est alors montré, pas masqué). */
  traduit: boolean;
  /** Catégorie pour les filtres (moi / adversaire / effet automatique). */
  categorie: CategorieLigne;
  /** Les `instance_id` des cartes citées (contexte d'accessibilité et usage aval). */
  refs: string[];
  /**
   * L'`instance_id` de la **carte de base** du Pokémon concerné, à mettre en évidence sur le plateau
   * quand la ligne est survolée (liaison journal ↔ plateau) — `null` si la ligne ne désigne aucun
   * Pokémon en jeu (on n'invente jamais une surbrillance).
   */
  surligne: string | null;
  /**
   * Le **détail du calcul des dégâts** (R-10.9), consultable pour chaque attaque — p.ex.
   * « 60 base, ×2 faiblesse, −30 résistance = 90 ». `null` quand la ligne n'est pas une attaque.
   */
  detailDegats: string | null;
};

/** Ce qu'un traducteur produit à partir des `donnees` d'un événement. */
type Traduction = {
  texte: string;
  refs?: string[];
  surligne?: string | null;
  detailDegats?: string | null;
};

/** Un traducteur d'un type d'événement : dit s'il est automatique, et rend sa phrase française. */
type Traducteur = {
  /** `true` pour un effet automatique du jeu (catégorie « auto », indépendant d'un joueur). */
  automatique: boolean;
  /** Construit la phrase à partir des données, en se plaçant du point de vue du destinataire `pour`. */
  traduire: (d: Record<string, unknown>, pour: string) => Traduction;
};

// --- Petites aides de lecture (tolérantes à la forme JSON native) -------------

/** Lit une chaîne de `donnees`, ou `undefined` si absente / d'un autre type (jamais une supposition). */
function chaine(d: Record<string, unknown>, cle: string): string | undefined {
  const v = d[cle];
  return typeof v === "string" ? v : undefined;
}

/** Lit un entier de `donnees`, ou `undefined` si absent / non numérique. */
function nombre(d: Record<string, unknown>, cle: string): number | undefined {
  const v = d[cle];
  return typeof v === "number" ? v : undefined;
}

/** Vrai si l'événement concerne le destinataire de la vue (`donnees.joueur === pour`). */
function estMoi(d: Record<string, unknown>, pour: string): boolean {
  return chaine(d, "joueur") === pour;
}

/** Le sujet d'une phrase de coup : « Tu » pour soi, « L'adversaire » sinon. */
function sujet(d: Record<string, unknown>, pour: string): string {
  return estMoi(d, pour) ? "Tu" : "L'adversaire";
}

/** Désigne l'Actif d'un joueur : « ton Actif » pour soi, « l'Actif adverse » sinon. */
function actifDe(joueur: string | undefined, pour: string): string {
  return joueur === pour ? "ton Actif" : "l'Actif adverse";
}

/** Nom français d'une phase du tour (codes du moteur), ou le code tel quel s'il est inconnu. */
function frPhase(code: string | undefined): string {
  const phases: Record<string, string> = {
    pioche: "pioche",
    principale: "principale",
    attaque: "attaque",
    checkup: "Checkup",
  };
  return (code && phases[code]) ?? code ?? "?";
}

/** Phrase courte d'une raison de fin de partie (R-14), ou la raison brute si elle est inconnue. */
function frRaison(code: string | undefined): string {
  const raisons: Record<string, string> = {
    abandon: "abandon",
    pioche_impossible: "pioche impossible",
    plus_de_pokemon: "plus de Pokémon en jeu",
    derniere_recompense: "dernière récompense prise",
    temps_ecoule: "temps écoulé",
    desertion: "désertion",
    inactivite: "partie inactive",
  };
  return (code && raisons[code]) ?? code ?? "?";
}

// --- Le registre des traducteurs, un par type d'événement --------------------
//
// L'ordre ici n'a pas d'importance ; ce qui compte est que TOUT type que le serveur peut diffuser
// (registre `PROJECTEURS` de `pbm_game.sortie.evenements`) y figure. Le test de parité côté moteur
// casse en CI si un événement projetable n'a pas sa traduction (« un test qui échoue sur un
// événement non traduit » plutôt qu'un identifiant brut servi au joueur).

export const TRADUCTEURS: Record<string, Traducteur> = {
  pioche_melangee: {
    automatique: true,
    traduire: (d, pour) => {
      const t = nombre(d, "taille");
      const combien = typeof t === "number" ? ` (${t} cartes)` : "";
      return {
        texte: estMoi(d, pour)
          ? `Tu mélanges ta pioche${combien}.`
          : `L'adversaire mélange sa pioche${combien}.`,
      };
    },
  },

  cartes_piochees: {
    automatique: false,
    traduire: (d, pour) => {
      const n = nombre(d, "nombre") ?? 0;
      const ids = Array.isArray(d.instance_ids)
        ? (d.instance_ids.filter((x): x is string => typeof x === "string"))
        : [];
      return {
        texte: estMoi(d, pour)
          ? `Tu pioches ${n} carte${n > 1 ? "s" : ""}.`
          : `L'adversaire pioche ${n} carte${n > 1 ? "s" : ""}.`,
        refs: ids,
      };
    },
  },

  phase_avancee: {
    automatique: true,
    traduire: (d) => {
      const num = nombre(d, "numero");
      const tour = typeof num === "number" ? ` (tour ${num})` : "";
      return { texte: `Phase : ${frPhase(chaine(d, "de"))} → ${frPhase(chaine(d, "vers"))}${tour}.` };
    },
  },

  tour_commence: {
    automatique: true,
    traduire: (d, pour) => {
      const num = nombre(d, "numero");
      const actif = chaine(d, "joueur_actif");
      const aQui = actif === pour ? "à toi de jouer" : "au tour de l'adversaire";
      return { texte: `Début du tour ${num ?? "?"} — ${aQui}.` };
    },
  },

  attaque_declaree: {
    automatique: false,
    traduire: (d, pour) => ({
      texte: estMoi(d, pour) ? "Tu déclares une attaque." : "L'adversaire déclare une attaque.",
    }),
  },

  confusion_resolue: {
    automatique: true,
    traduire: (d, pour) => {
      const cible = actifDe(chaine(d, "joueur"), pour);
      const annulee = d.attaque_annulee === true;
      const deg = nombre(d, "degats") ?? 0;
      const texte = annulee
        ? `Confusion (R-11.5) : pile — l'attaque de ${cible} est annulée${
            deg > 0 ? `, ${deg} dégâts d'auto-blessure` : ""
          }.`
        : `Confusion (R-11.5) : face — ${cible} attaque normalement.`;
      return { texte };
    },
  },

  degats: {
    automatique: false,
    traduire: (d) => {
      const deg = nombre(d, "degats") ?? 0;
      const compteurs = nombre(d, "compteurs");
      const detail = chaine(d, "detail") ?? null;
      const cible = chaine(d, "cible") ?? null;
      const suffixe = typeof compteurs === "number" ? ` (${compteurs} compteur${compteurs > 1 ? "s" : ""})` : "";
      return {
        texte: `Dégâts : ${deg}${suffixe}.`,
        detailDegats: detail,
        surligne: cible,
        refs: cible ? [cible] : [],
      };
    },
  },

  partie_terminee: {
    automatique: true,
    traduire: (d, pour) => {
      const vainqueur = chaine(d, "vainqueur");
      const issue =
        vainqueur == null
          ? "égalité"
          : vainqueur === pour
            ? "tu gagnes"
            : "l'adversaire gagne";
      const par = chaine(d, "abandon_par");
      const abandon = par ? `, abandon de ${par === pour ? "toi" : "l'adversaire"}` : "";
      return { texte: `Partie terminée — ${issue} (${frRaison(chaine(d, "raison"))}${abandon}).` };
    },
  },

  retraite_effectuee: {
    automatique: false,
    traduire: (d, pour) => {
      const cout = nombre(d, "cout");
      const defaussees = Array.isArray(d.energies_defaussees) ? d.energies_defaussees.length : 0;
      const nouvel = chaine(d, "nouvel_actif") ?? null;
      const ancien = chaine(d, "ancien_actif");
      const refs = [ancien, nouvel].filter((x): x is string => typeof x === "string");
      return {
        texte:
          `${sujet(d, pour)} ${estMoi(d, pour) ? "bats" : "bat"} en retraite` +
          `${typeof cout === "number" ? ` (coût ${cout})` : ""}` +
          `${defaussees > 0 ? `, ${defaussees} énergie${defaussees > 1 ? "s" : ""} défaussée${defaussees > 1 ? "s" : ""}` : ""}.`,
        surligne: nouvel,
        refs,
      };
    },
  },

  promotion_effectuee: {
    automatique: false,
    traduire: (d, pour) => {
      const nouvel = chaine(d, "nouvel_actif") ?? null;
      return {
        texte: `${sujet(d, pour)} ${estMoi(d, pour) ? "promeus" : "promeut"} un Pokémon du banc comme Actif.`,
        surligne: nouvel,
        refs: nouvel ? [nouvel] : [],
      };
    },
  },

  echange_force_effectue: {
    automatique: false,
    traduire: (d, pour) => {
      const nouvel = chaine(d, "nouvel_actif") ?? null;
      const ancien = chaine(d, "ancien_actif");
      const refs = [ancien, nouvel].filter((x): x is string => typeof x === "string");
      return {
        texte: `${sujet(d, pour)} ${estMoi(d, pour) ? "subis" : "subit"} un échange forcé d'Actif (R-8.8).`,
        surligne: nouvel,
        refs,
      };
    },
  },

  etat_checkup: {
    automatique: true,
    traduire: (d, pour) => {
      const etat = chaine(d, "etat") ?? "?";
      const cible = actifDe(chaine(d, "joueur"), pour);
      const regle = chaine(d, "regle");
      const r = regle ? ` (${regle})` : "";
      const deg = nombre(d, "degats") ?? 0;
      const gueri = d.gueri === true;
      const nom = ETATS[etat]?.label ?? etat;
      let texte: string;
      switch (etat) {
        case "empoisonne":
          texte = `Poison sur ${cible} : ${deg} dégâts${r}.`;
          break;
        case "brule":
          texte = `Brûlure sur ${cible} : ${deg} dégâts${gueri ? ", puis guérie" : ""}${r}.`;
          break;
        case "endormi":
          texte = `Sommeil de ${cible} : ${gueri ? "réveil" : "reste endormi"}${r}.`;
          break;
        case "paralyse":
          texte = `Paralysie de ${cible} : ${gueri ? "dissipée" : "persiste"}${r}.`;
          break;
        default:
          texte = `${nom} sur ${cible}${r}.`;
      }
      return { texte };
    },
  },

  effet_expire: {
    automatique: true,
    // Aucun effet temporaire au jalon J1 (les données sont vides) : on journalise tout de même
    // l'expiration pour qu'un effet « jusqu'à la fin de ce tour » ne disparaisse jamais en silence.
    traduire: () => ({ texte: "Un effet temporaire expire (R-12.5)." }),
  },

  ko: {
    automatique: true,
    traduire: (d, pour) => {
      const cible = actifDe(chaine(d, "joueur"), pour);
      const pokemon = chaine(d, "pokemon") ?? null;
      const prises = nombre(d, "recompenses_prises") ?? 0;
      const par = chaine(d, "par");
      const recompenses =
        prises > 0
          ? ` — ${par === pour ? "tu prends" : "l'adversaire prend"} ${prises} récompense${prises > 1 ? "s" : ""}`
          : "";
      return {
        texte: `${cible} est mis K.O.${recompenses} (R-13.1).`,
        surligne: pokemon,
        refs: pokemon ? [pokemon] : [],
      };
    },
  },

  promotion_requise: {
    automatique: true,
    traduire: (d, pour) => ({
      texte: `${estMoi(d, pour) ? "Tu dois" : "L'adversaire doit"} promouvoir un Pokémon du banc (R-8.7).`,
    }),
  },

  pokemon_pose: {
    automatique: false,
    traduire: (d, pour) => {
      const ref = chaine(d, "ref");
      const pokemon = chaine(d, "pokemon") ?? null;
      const zone = chaine(d, "zone") === "actif" ? "comme Actif" : "au banc";
      const nom = ref ? ` ${ref}` : " un Pokémon";
      return {
        texte: `${sujet(d, pour)} ${estMoi(d, pour) ? "places" : "place"}${nom} ${zone}.`,
        surligne: pokemon,
        refs: pokemon ? [pokemon] : [],
      };
    },
  },

  evolution: {
    automatique: false,
    traduire: (d, pour) => {
      const base = chaine(d, "base") ?? null;
      const nom = chaine(d, "nom") ?? chaine(d, "vers");
      return {
        texte: `${sujet(d, pour)} ${estMoi(d, pour) ? "fais" : "fait"} évoluer un Pokémon${
          nom ? ` en ${nom}` : ""
        }.`,
        surligne: base,
        refs: base ? [base] : [],
      };
    },
  },
};

/**
 * Les types d'événement que ce module sait traduire — exactement les clés de {@link TRADUCTEURS}.
 *
 * Le test de parité côté moteur (`apps/game/tests/test_parite_journal_front.py`) lit cette liste
 * dans le source et vérifie que **tout** événement projetable (`PROJECTEURS`) y figure : ajouter un
 * événement au moteur sans sa traduction ici casse la CI, au lieu de servir un identifiant brut.
 */
export const TYPES_EVENEMENT_CONNUS: readonly string[] = Object.keys(TRADUCTEURS);

/** L'auteur d'un coup : le premier `donnees.joueur` trouvé parmi ses événements (ordre du coup). */
function auteurDuCoup(evenements: unknown[]): string | undefined {
  for (const e of evenements) {
    const evt = e as EvenementJournal | null;
    const joueur = evt?.donnees?.joueur;
    if (typeof joueur === "string") return joueur;
  }
  return undefined;
}

/**
 * Traduit un seul événement en ligne de journal.
 *
 * `pour` est le destinataire de la vue (pour dire « toi » vs « l'adversaire ») ; `auteurCoup` est
 * l'auteur du coup, utilisé comme repli de camp **uniquement** pour les événements qui ne portent
 * pas eux-mêmes de `joueur` (les dégâts portent la cible, pas l'attaquant). Un type inconnu produit
 * une ligne `traduit: false` qui montre l'identifiant brut — jamais masquée (pas de repli silencieux).
 */
export function traduireEvenement(
  evt: EvenementJournal,
  index: number,
  numero: number,
  pour: string,
  auteurCoup: string | undefined,
): LigneJournal {
  const type = evt.type ?? "";
  const donnees = evt.donnees ?? {};
  const cle = `${numero}-${index}`;
  const traducteur = TRADUCTEURS[type];

  if (!traducteur) {
    // Pas de traduction : on montre l'identifiant technique plutôt que de prétendre comprendre.
    return {
      cle,
      numero,
      type,
      texte: `Événement non traduit : ${type || "(type absent)"}`,
      traduit: false,
      categorie: "auto",
      refs: [],
      surligne: null,
      detailDegats: null,
    };
  }

  const t = traducteur.traduire(donnees, pour);
  let categorie: CategorieLigne;
  if (traducteur.automatique) {
    categorie = "auto";
  } else {
    const joueur = chaine(donnees, "joueur") ?? auteurCoup;
    categorie = joueur === undefined ? "auto" : joueur === pour ? "moi" : "adversaire";
  }

  return {
    cle,
    numero,
    type,
    texte: t.texte,
    traduit: true,
    categorie,
    refs: t.refs ?? [],
    surligne: t.surligne ?? null,
    detailDegats: t.detailDegats ?? null,
  };
}

/**
 * Construit le fil complet du journal à partir des coups diffusés, dans l'ordre.
 *
 * Chaque événement d'un coup devient une ligne ; l'auteur du coup (déduit de ses événements) sert de
 * repli de camp pour les événements sans `joueur`. Les coups sont supposés déjà dédupliqués et
 * ordonnés par le canal temps réel (invariant du numéro de séquence, voir `realtime.ts`).
 */
export function construireJournal(coups: CoupJournal[], pour: string): LigneJournal[] {
  const lignes: LigneJournal[] = [];
  for (const coup of coups) {
    const auteur = auteurDuCoup(coup.evenements);
    coup.evenements.forEach((e, i) => {
      lignes.push(traduireEvenement((e ?? {}) as EvenementJournal, i, coup.numero, pour, auteur));
    });
  }
  return lignes;
}
