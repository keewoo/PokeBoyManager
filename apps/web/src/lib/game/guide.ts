/**
 * La **première partie guidée** (lot `j-plateau-aide`), module pur.
 *
 * Le parcours que demande la fiche du lot — poser, attacher, attaquer, prendre une récompense — est
 * décrit ici comme une suite d'étapes, chacune avec sa consigne et un **constat** : « est-ce fait ? »,
 * lu dans la vue projetée. Trois choix de conception, et chacun répond à un critère du lot.
 *
 * 1. **Le guide constate, il ne pilote pas.** Une étape ne porte aucune action : elle dit quoi faire
 *    et reconnaît que c'est fait. Le joueur joue ses coups lui-même, par la barre d'actions
 *    habituelle — l'aide ne joue jamais à sa place (troisième critère d'acceptation).
 * 2. **La progression ne recule jamais.** `accompli` regarde l'état courant, et un état peut
 *    redevenir faux (l'Actif adverse remplacé n'a plus de dégâts). Sans mémoire, le guide
 *    renverrait le joueur à une étape déjà franchie — pire qu'une absence de guide. D'où
 *    {@link avancerGuide}, qui ne prend que le maximum entre l'étape atteinte et l'étape constatée.
 * 3. **Les consignes viennent du corpus.** Chaque étape cite le `R-x.y` qu'elle enseigne, et ce
 *    `R-x.y` doit exister dans `docs/jeu/REGLES.md` — `test_parite_aide_front.py` le vérifie, comme
 *    pour les explications de refus. Une consigne inventée d'après le code finirait par enseigner
 *    une règle qui n'est pas celle appliquée (le risque nommé par la fiche du lot).
 *
 * Tout est pur (aucune E/S, aucun React) : la progression entière se rejoue dans un test.
 */

import { RECOMPENSES_MAX, separerCamps, type VuePartie } from "@/lib/game/plateau";

/** Une étape du parcours guidé : ce qu'on demande, et comment on sait que c'est fait. */
export type EtapeGuide = {
  /** Identifiant stable de l'étape (sert de clé de rendu et de repère dans les tests). */
  cle: string;
  /** Le titre court affiché en tête du guide. */
  titre: string;
  /** La consigne, à la deuxième personne, sans numéro de règle ni jargon. */
  consigne: string;
  /** La règle du corpus que cette étape enseigne (`docs/jeu/REGLES.md`). */
  regle: string;
  /**
   * Vrai quand l'étape est franchie, **constaté sur la vue** — jamais sur une action qu'on aurait
   * déclenchée. Doit tolérer une vue incomplète : une vue qui n'a pas encore d'Actif n'est pas une
   * erreur, c'est le début de la partie.
   */
  accompli: (vue: VuePartie) => boolean;
};

/**
 * Le parcours de la première partie, dans l'ordre.
 *
 * Il s'arrête à la première récompense prise : à ce moment le joueur a fait le tour complet de la
 * boucle du jeu (poser → attacher → attaquer → prendre), et il sait comment on gagne. Continuer à
 * le guider après serait du bavardage.
 */
export const ETAPES_GUIDE: readonly EtapeGuide[] = [
  {
    cle: "actif",
    titre: "Pose ton premier Pokémon",
    consigne:
      "Choisis dans ta main un Pokémon de base et pose-le devant toi. C'est ton Actif : c'est lui " +
      "qui attaque, et c'est lui qu'on attaque.",
    regle: "R-4.2",
    accompli: (vue) => camp(vue)?.actif != null,
  },
  {
    cle: "banc",
    titre: "Remplis un peu ton banc",
    consigne:
      "Pose un ou deux autres Pokémon de base sur ton banc, à côté. Ils attendent là : si ton " +
      "Actif tombe, l'un d'eux prend sa place.",
    regle: "R-3.2",
    accompli: (vue) => (camp(vue)?.banc.length ?? 0) >= 1,
  },
  {
    cle: "energie",
    titre: "Attache une énergie",
    consigne:
      "Prends une carte Énergie dans ta main et attache-la à ton Actif. Sans énergie, il ne peut " +
      "pas attaquer — et tu n'as droit qu'à une seule énergie par tour.",
    regle: "R-5.4",
    accompli: (vue) => (camp(vue)?.actif?.energies.length ?? 0) >= 1,
  },
  {
    cle: "attaque",
    titre: "Attaque le Pokémon d'en face",
    consigne:
      "Ton Actif a assez d'énergie ? Choisis son attaque et lance-la sur le Pokémon d'en face. " +
      "Attention : l'attaque termine ton tour.",
    regle: "R-9.1",
    accompli: (vue) => degatsEnFace(vue) > 0 || recompensesPrises(vue) > 0,
  },
  {
    cle: "recompense",
    titre: "Prends ta récompense",
    consigne:
      "Quand le Pokémon d'en face tombe K.O., tu prends une de tes six cartes récompense. Les six " +
      "prises, tu gagnes la partie.",
    regle: "R-13.3",
    accompli: (vue) => recompensesPrises(vue) > 0,
  },
];

/**
 * Le camp du destinataire de la vue, ou `null` si la vue ne permet pas de le trancher.
 *
 * `separerCamps` **lève** sur une vue incohérente, et c'est bien : un plateau à moitié défini doit
 * se signaler. Mais le guide est un décor posé par-dessus le jeu : s'il levait, il ferait tomber
 * l'écran entier pour une aide. On attrape donc ici, et on rend `null` — l'étape se dit « pas
 * encore faite », ce qui est la lecture juste pour une vue qu'on n'a pas su lire.
 */
function camp(vue: VuePartie) {
  try {
    return separerCamps(vue).moi;
  } catch {
    return null;
  }
}

/** Les dégâts marqués sur l'Actif adverse (0 s'il n'y en a pas, ou si la vue est illisible). */
function degatsEnFace(vue: VuePartie): number {
  try {
    return separerCamps(vue).adversaire.actif?.compteurs_degats ?? 0;
  } catch {
    return 0;
  }
}

/** Combien de récompenses le joueur a déjà prises (les siennes restantes partent de six). */
function recompensesPrises(vue: VuePartie): number {
  const moi = camp(vue);
  if (!moi) return 0;
  return Math.max(0, RECOMPENSES_MAX - moi.recompenses_nombre);
}

/**
 * La clé de mémoire du navigateur qui retient que le parcours guidé a déjà été vu.
 *
 * Préfixée par le projet pour ne pas entrer en collision avec une autre clé du domaine.
 */
export const CLE_GUIDE_VU = "pbm.jeu.guide-vu";

/**
 * Faut-il guider ce joueur, c'est-à-dire : est-ce sa première partie ?
 *
 * Le stockage est **injecté** plutôt que lu globalement : c'est ce qui rend cette décision testable
 * sans navigateur, et c'est aussi ce qui permet à l'appelant de passer `null` côté serveur (rendu
 * Next.js) sans tomber sur un `localStorage` inexistant.
 *
 * **Stockage illisible = on guide.** Un navigateur en navigation privée peut lever sur `getItem` ;
 * on ne sait alors pas si le joueur a déjà joué. Entre proposer un guide à qui n'en a plus besoin
 * (il le replie) et le refuser à un enfant qui débute (il reste bloqué), le choix est fait — et il
 * est écrit ici plutôt que caché dans un `catch` muet.
 */
export function estPremierePartie(stockage: Pick<Storage, "getItem"> | null | undefined): boolean {
  if (!stockage) return true;
  try {
    return stockage.getItem(CLE_GUIDE_VU) === null;
  } catch {
    return true;
  }
}

/**
 * Note que le parcours guidé a été vu : les parties suivantes ne l'ouvrent plus d'elles-mêmes.
 *
 * L'aide reste accessible — c'est l'ouverture automatique qui cesse. Un échec d'écriture n'est pas
 * remonté : il ne prive le joueur de rien (au pire le guide s'ouvrira encore), et faire échouer un
 * écran de jeu pour une préférence d'affichage serait disproportionné.
 */
export function marquerGuideVu(stockage: Pick<Storage, "setItem"> | null | undefined): void {
  if (!stockage) return;
  try {
    stockage.setItem(CLE_GUIDE_VU, "1");
  } catch {
    // Mémoire indisponible (navigation privée, quota) : sans effet pour le joueur.
  }
}

/** Où en est le joueur dans le parcours guidé. */
export type ProgressionGuide = {
  /** L'index de l'étape en cours, ou `ETAPES_GUIDE.length` quand le parcours est terminé. */
  index: number;
  /** L'étape en cours, `null` quand le parcours est terminé. */
  etape: EtapeGuide | null;
  /** Vrai quand les cinq étapes sont franchies : le guide se retire de lui-même. */
  termine: boolean;
};

/**
 * Avance le parcours à partir de l'étape déjà atteinte, sans jamais reculer.
 *
 * On part de `atteint` (ce que l'appelant a mémorisé) et on avance tant que l'étape courante est
 * constatée faite. Le résultat est donc monotone : une fois franchie, une étape le reste, même si
 * l'état du plateau change ensuite (un Actif adverse remplacé, une évolution qui efface les dégâts).
 *
 * @param vue la vue projetée pour ce joueur
 * @param atteint l'index déjà atteint (0 au premier appel)
 */
export function avancerGuide(vue: VuePartie, atteint = 0): ProgressionGuide {
  let index = Math.min(Math.max(0, atteint), ETAPES_GUIDE.length);
  for (;;) {
    const etape = ETAPES_GUIDE[index];
    if (!etape || !etape.accompli(vue)) break;
    index += 1;
  }
  const etape = ETAPES_GUIDE[index] ?? null;
  return { index, etape, termine: etape === null };
}
