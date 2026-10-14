/**
 * Aide en jeu **pure** (lot `j-plateau-aide`) : pourquoi je ne peux pas faire ça, et que
 * puis-je faire.
 *
 * Ce module porte les **textes** de l'aide, et c'est délibéré : ils sont écrits une seule fois,
 * là où ils s'affichent. Trois garanties tiennent ce fichier, et chacune est vérifiée par un test.
 *
 * 1. **Les explications viennent du corpus, pas du code.** Chaque entrée de {@link EXPLICATIONS}
 *    traduit une règle `R-x.y` de `docs/jeu/REGLES.md` — c'est le risque nommé par la fiche du lot :
 *    une aide écrite d'après le code finit par expliquer des règles qui ne sont pas celles
 *    appliquées. La garde est côté moteur : `apps/game/tests/test_parite_aide_front.py` lit CE
 *    fichier, extrait les règles que le moteur peut citer dans un refus, et échoue si l'une d'elles
 *    n'a pas d'explication — ou si une explication cite une règle absente du corpus. Même idiome que
 *    `test_parite_journal_front.py` pour le journal.
 * 2. **L'aide ne joue jamais le coup à la place du joueur.** {@link Suggestion} ne porte que de
 *    quoi *afficher* un coup (son type et son étiquette), **jamais** ses `params` : il n'y a donc
 *    rien ici qu'un appelant pourrait soumettre au serveur. C'est une garantie de structure, pas
 *    une intention.
 * 3. **Rien n'est redérivé.** Les coups proposés sortent de `vue.actions_legales`, que le serveur
 *    a calculés (il fait autorité) ; l'aide les ordonne et les met en mots, elle n'en invente aucun.
 *
 * Tout est pur (aucune E/S, aucun React) : testable sans navigateur.
 */

import { RECOMPENSES_MAX, type VuePartie } from "@/lib/game/plateau";

/**
 * L'objectif de la partie, en une phrase — le « rappel de l'objectif » demandé par la fiche du lot.
 *
 * Un enfant de onze ans qui ne connaît pas les règles perd d'abord le *but* : il joue des cartes
 * sans savoir ce qui le fait gagner. Cette phrase reste affichée.
 */
export const OBJECTIF =
  `Prends tes ${RECOMPENSES_MAX} cartes récompense avant l'adversaire : c'est comme ça qu'on gagne.`;

/**
 * Une règle du corpus traduite pour un enfant, avec une porte de sortie.
 *
 * `regle` est le niveau que le **moteur cite** : une règle (`R-5.4`) ou, pour quelques refus, la
 * section qui la contient (`R-5`). On explique le niveau cité, jamais un niveau deviné.
 */
export type Explication = {
  /** L'identifiant du corpus (`docs/jeu/REGLES.md`) que cette explication traduit. */
  regle: string;
  /** Le titre court, tel qu'un enfant le dirait (« Une seule énergie par tour »). */
  titre: string;
  /** La règle en une ou deux phrases simples, sans jargon et sans numéro de règle. */
  explication: string;
  /**
   * Ce que le joueur **peut** faire malgré ce refus.
   *
   * Jamais « attends » : un refus qui ne rouvre aucune porte est exactement ce qui fait désinstaller
   * un jeu. Cette phrase est la moitié utile de l'aide.
   */
  alternative: string;
  /** Les mots du jeu employés ici, qui ont tous leur entrée au {@link GLOSSAIRE}. */
  mots: string[];
};

/**
 * Les explications, par règle du corpus.
 *
 * **Toute règle que le moteur peut citer dans un refus doit figurer ici** — c'est le premier
 * critère d'acceptation du lot, et `test_parite_aide_front.py` le prouve en lisant ce fichier. On
 * explique volontiers plus que le strict nécessaire (une règle citée nulle part aujourd'hui peut
 * l'être demain), jamais moins.
 */
export const EXPLICATIONS: Record<string, Explication> = {
  "R-3.2": {
    regle: "R-3.2",
    titre: "Cinq Pokémon au plus sur le banc",
    explication:
      "Ton banc a cinq places, pas plus. Les Pokémon qui y sont attendent : ils ne peuvent pas " +
      "attaquer tant qu'ils ne sont pas devenus ton Actif.",
    alternative: "Ton banc est plein : fais évoluer un de ceux qui y sont, ou attaque.",
    mots: ["Banc", "Actif"],
  },
  "R-3.5": {
    regle: "R-3.5",
    titre: "Un seul Stade sur la table",
    explication:
      "Il n'y a qu'un seul Stade en jeu, et il sert aux deux joueurs. En poser un nouveau jette " +
      "l'ancien — et tu ne peux pas poser un Stade qui porte le même nom que celui déjà là.",
    alternative: "Pose un Stade d'un autre nom, ou garde celui-ci pour plus tard.",
    mots: ["Stade"],
  },
  "R-3.7": {
    regle: "R-3.7",
    titre: "Un seul Outil par Pokémon",
    explication: "Chaque Pokémon ne porte qu'un seul Outil à la fois.",
    alternative:
      "Attache cet Outil à un Pokémon qui n'en a pas encore, ou retire d'abord celui qu'il porte.",
    mots: ["Outil"],
  },
  "R-4.1": {
    regle: "R-4.1",
    titre: "On commence par mélanger et piocher sept cartes",
    explication:
      "Tout au début, chacun mélange ses soixante cartes et en pioche sept. C'est la mise en place.",
    alternative: "Laisse la mise en place se terminer : tu joueras juste après.",
    mots: ["Pioche", "Main"],
  },
  "R-4.2": {
    regle: "R-4.2",
    titre: "Ton Actif doit être un Pokémon de base",
    explication:
      "Pour démarrer, tu dois poser un Pokémon de base devant toi : c'est ton Actif, celui qui " +
      "attaque et qui se fait attaquer. Tu peux en poser jusqu'à cinq autres sur ton banc.",
    alternative:
      "Cherche dans ta main une carte Pokémon de base — celle qui n'est l'évolution de personne.",
    mots: ["Actif", "Pokémon de base", "Banc"],
  },
  "R-5": {
    // Quatre refus du moteur (famille « talent », `pbm_game/actions/familles_jeu.py`) citent la
    // SECTION « Déroulé d'un tour (R-5) » plutôt qu'une de ses règles. Le message du moteur, lui,
    // porte le détail précis (« Seul le joueur actif active un talent (R-5.1). ») et s'affiche
    // au-dessus de cette explication : le joueur a donc bien le pourquoi exact. On explique le
    // niveau cité tel qu'il est, au lieu de deviner laquelle des six règles de la section vaut —
    // ce serait une aide qui dit autre chose que ce que le moteur applique (le risque du lot).
    regle: "R-5",
    titre: "Chaque chose à son moment du tour",
    explication:
      "Un tour suit toujours le même chemin : d'abord la pioche, puis le moment où tu joues ce que " +
      "tu veux, puis l'attaque qui le termine. Et on ne joue que pendant son propre tour.",
    alternative:
      "Regarde où tu en es dans ton tour, ou attends que l'adversaire ait fini le sien.",
    mots: ["Tour", "Phase", "Talent"],
  },
  "R-5.1": {
    regle: "R-5.1",
    titre: "Un tour, trois temps",
    explication:
      "Chaque tour se passe dans cet ordre : tu pioches une carte, tu joues ce que tu veux, " +
      "puis tu attaques — et l'attaque termine ton tour.",
    alternative: "Ce n'est pas le moment de ce coup. Regarde « Que puis-je faire ? » juste à côté.",
    mots: ["Tour", "Phase"],
  },
  "R-5.2": {
    regle: "R-5.2",
    titre: "Pioche d'abord",
    explication:
      "Au début de ton tour, tu dois piocher une carte avant de faire quoi que ce soit d'autre.",
    alternative: "Pioche ta carte : tout le reste du tour s'ouvre juste après.",
    mots: ["Pioche"],
  },
  "R-5.3": {
    regle: "R-5.3",
    titre: "La phase principale : dans l'ordre que tu veux",
    explication:
      "Pendant la phase principale tu peux poser des Pokémon sur ton banc, faire évoluer, " +
      "attacher une énergie, jouer des cartes Dresseur, battre en retraite et utiliser des " +
      "talents — dans l'ordre que tu préfères.",
    alternative: "Va jusqu'à la phase principale, puis reviens à ce coup.",
    mots: ["Phase", "Banc", "Évolution", "Énergie", "Dresseur", "Retraite", "Talent"],
  },
  "R-5.4": {
    regle: "R-5.4",
    titre: "Une seule énergie par tour",
    explication: "Tu n'attaches qu'une seule carte Énergie par tour, à un seul Pokémon.",
    alternative:
      "Tu l'as déjà fait ce tour-ci. Fais autre chose, puis attaque ou termine ton tour.",
    mots: ["Énergie"],
  },
  "R-5.5": {
    regle: "R-5.5",
    titre: "Un seul Supporter par tour",
    explication:
      "Un seul Supporter par tour, et un seul Stade par tour. Les Objets et les Outils, eux, tu " +
      "peux en jouer autant que tu veux.",
    alternative: "Joue un Objet ou un Outil à la place, ou garde ton Supporter pour ton prochain tour.",
    mots: ["Supporter", "Stade", "Objet", "Outil"],
  },
  "R-5.6": {
    regle: "R-5.6",
    titre: "Une seule retraite par tour",
    explication:
      "Tu ne ramènes ton Actif au banc par une retraite qu'une fois par tour.",
    alternative: "Tu l'as déjà fait ce tour-ci. Attaque, ou termine ton tour.",
    mots: ["Retraite", "Actif", "Banc"],
  },
  "R-6.1": {
    regle: "R-6.1",
    titre: "Pas d'attaque au tout premier tour",
    explication:
      "Le joueur qui commence la partie n'attaque pas à son premier tour : ce serait trop fort " +
      "d'avoir le premier coup et la première attaque.",
    alternative: "Pose des Pokémon, attache une énergie, puis termine ton tour.",
    mots: ["Tour", "Attaque"],
  },
  "R-6.2": {
    regle: "R-6.2",
    titre: "Pas de Supporter au tout premier tour",
    explication:
      "Le joueur qui commence la partie ne joue pas de carte Supporter à son premier tour.",
    alternative: "Joue un Objet, pose un Pokémon sur ton banc, ou termine ton tour.",
    mots: ["Supporter", "Objet", "Banc"],
  },
  "R-6.5": {
    regle: "R-6.5",
    titre: "Pas d'évolution au premier tour",
    explication:
      "Personne ne fait évoluer un Pokémon à son premier tour — même le joueur qui joue en second.",
    alternative: "Pose le Pokémon maintenant : tu le feras évoluer à ton prochain tour.",
    mots: ["Évolution", "Tour"],
  },
  "R-7.1": {
    regle: "R-7.1",
    titre: "Une évolution garde tout",
    explication:
      "Pour faire évoluer un Pokémon, tu poses sa carte d'évolution dessus. Il garde ses énergies, " +
      "ses cartes attachées et ses dégâts : rien ne se perd.",
    alternative: "Pose la carte d'évolution sur le Pokémon dont elle porte le nom.",
    mots: ["Évolution", "Énergie", "Compteur de dégâts"],
  },
  "R-7.3": {
    regle: "R-7.3",
    titre: "Un Pokémon qui vient d'arriver n'évolue pas",
    explication:
      "Un Pokémon posé pendant ce tour est « nouveau en jeu » : il ne peut pas évoluer avant ton " +
      "prochain tour.",
    alternative: "Laisse-le sur ton banc : il pourra évoluer à ton prochain tour.",
    mots: ["Évolution", "Banc", "Tour"],
  },
  "R-7.4": {
    regle: "R-7.4",
    titre: "Une seule évolution par Pokémon et par tour",
    explication: "Un même Pokémon n'évolue pas deux fois dans le même tour.",
    alternative: "Il pourra évoluer encore à ton prochain tour.",
    mots: ["Évolution", "Tour"],
  },
  "R-8.2": {
    regle: "R-8.2",
    titre: "La retraite coûte des énergies",
    explication:
      "Pour ramener ton Actif sur le banc, tu défausses autant d'énergies que son coût de retraite " +
      "le demande — à toi de choisir lesquelles. Le Pokémon qui descend garde ses dégâts et ses " +
      "cartes attachées.",
    alternative: "Attache d'abord une énergie, ou choisis un autre coup.",
    mots: ["Retraite", "Actif", "Banc", "Énergie", "Défausse", "Compteur de dégâts"],
  },
  "R-8.7": {
    regle: "R-8.7",
    titre: "Il faut remplacer un Pokémon K.O.",
    explication:
      "Quand ton Actif tombe K.O., tu dois choisir un Pokémon de ton banc pour prendre sa place. " +
      "Ce n'est pas un choix facultatif : la partie attend ta réponse.",
    alternative: "Choisis sur ton banc le Pokémon qui devient ton nouvel Actif.",
    mots: ["Actif", "Banc", "K.O."],
  },
  "R-9.1": {
    regle: "R-9.1",
    titre: "Attaquer termine ton tour",
    explication:
      "Tu choisis une attaque de ton Actif dont le coût en énergies est payé, tu l'annonces — et " +
      "ton tour s'arrête là.",
    alternative: "Fais d'abord tout ce que tu veux faire ce tour-ci : l'attaque vient en dernier.",
    mots: ["Attaque", "Actif", "Coût", "Énergie", "Tour"],
  },
  "R-9.2": {
    regle: "R-9.2",
    titre: "Il faut assez d'énergie pour attaquer",
    explication:
      "Ton Actif doit porter au moins les énergies que l'attaque demande. Un symbole incolore " +
      "accepte n'importe quel type d'énergie, et certaines énergies spéciales comptent pour " +
      "plusieurs.",
    alternative: "Attache une énergie, ou choisis une attaque qui coûte moins cher.",
    mots: ["Énergie", "Attaque", "Coût", "Incolore"],
  },
  "R-13.3": {
    regle: "R-13.3",
    titre: "Un Pokémon mis K.O. te fait prendre une récompense",
    explication:
      "Quand tu mets un Pokémon adverse K.O., tu prends une de tes cartes récompense. Certaines " +
      "cartes en valent deux ou trois — c'est écrit sur la carte elle-même.",
    alternative: "Mets le Pokémon d'en face K.O. pour prendre une récompense de plus.",
    mots: ["Récompense", "K.O."],
  },
  "R-14.3": {
    regle: "R-14.3",
    titre: "Abandonner, c'est perdre tout de suite",
    explication:
      "Tu peux abandonner à n'importe quel moment, mais tu perds la partie immédiatement.",
    alternative:
      "Si tu hésites, ouvre « Que puis-je faire ? » : il reste peut-être un coup que tu n'avais pas vu.",
    mots: ["Tour"],
  },
  "R-14.6": {
    regle: "R-14.6",
    titre: "La partie est terminée",
    explication:
      "Une partie finie n'accepte plus aucun coup : son journal est clos, et le résultat ne change plus.",
    alternative: "Relis le résumé de la partie, ou lance-en une nouvelle.",
    mots: ["Tour"],
  },
  "R-15.12": {
    regle: "R-15.12",
    titre: "Je ne sais pas encore jouer cette carte",
    explication:
      "Quand l'effet d'une carte n'est pas encore programmé et vérifié, le jeu refuse la carte au " +
      "lieu de la jouer de travers. Mieux vaut dire « je ne sais pas » que se tromper.",
    alternative: "Choisis une autre carte : celle-ci n'est pas encore jouable.",
    mots: [],
  },
};

/**
 * Les mots du jeu, expliqués — le glossaire demandé par la fiche du lot.
 *
 * Il sert deux fois : à l'écran (le joueur cherche un mot), et comme garde — chaque mot cité par
 * une {@link Explication} doit avoir son entrée ici, sinon l'aide emploie un mot qu'elle n'explique
 * pas. `aide.test.ts` le vérifie.
 */
export const GLOSSAIRE: Record<string, string> = {
  Actif:
    "Le Pokémon posé devant toi, au milieu du plateau. C'est lui qui attaque et c'est lui qu'on attaque.",
  Attaque:
    "Ce que ton Actif fait au Pokémon d'en face. Elle coûte des énergies, et elle termine ton tour.",
  Banc:
    "Les cinq places à côté de ton Actif. Les Pokémon y attendent leur tour : ils ne peuvent pas attaquer de là.",
  Checkup:
    "Le petit moment entre deux tours où le poison, les brûlures, le sommeil et la paralysie font leur effet.",
  "Compteur de dégâts":
    "Les dégâts déjà reçus par un Pokémon. Quand ils atteignent ses points de vie, il tombe K.O.",
  Coût: "Les énergies qu'il faut avoir attachées pour pouvoir lancer une attaque, ou pour battre en retraite.",
  Défausse: "La pile des cartes utilisées ou perdues. Tout le monde peut la regarder.",
  Dresseur:
    "Une carte qui n'est ni un Pokémon ni une énergie : Objet, Supporter, Outil ou Stade. Elle fait une action.",
  Énergie:
    "La carte qu'on attache à un Pokémon pour lui permettre d'attaquer. Une seule par tour.",
  "État spécial":
    "Empoisonné, Brûlé, Endormi, Paralysé ou Confus : un ennui qui colle à un Pokémon et le gêne.",
  Évolution:
    "Poser une carte sur un Pokémon pour le transformer en sa version plus forte. Il garde tout ce qu'il portait.",
  Faiblesse:
    "Le type qui fait mal à un Pokémon : une attaque de ce type lui fait le double de dégâts.",
  Incolore:
    "Un symbole de coût qui accepte n'importe quel type d'énergie. Pratique : tout fait l'affaire.",
  "K.O.":
    "Un Pokémon à bout de points de vie. Il part à la défausse, et celui qui l'a mis K.O. prend une récompense.",
  Main: "Les cartes que tu tiens. L'adversaire n'en connaît que le nombre, jamais lesquelles.",
  Objet: "Une carte Dresseur qu'on joue autant qu'on veut dans le tour.",
  Outil: "Une carte Dresseur qu'on attache à un Pokémon pour l'améliorer. Un seul par Pokémon.",
  Phase:
    "Un morceau du tour : d'abord la pioche, puis la phase principale, puis l'attaque qui le termine.",
  Pioche: "Ta pile de cartes face cachée. Tu en prends une au début de chaque tour.",
  "Pokémon de base":
    "Un Pokémon qui n'est l'évolution de personne : c'est le seul qu'on peut poser directement.",
  Récompense:
    "Une des six cartes face cachée posées de ton côté. Tu en prends une à chaque Pokémon adverse mis K.O. ; les six prises, tu gagnes.",
  Résistance:
    "Le type qui fait moins mal à un Pokémon : une attaque de ce type lui fait 30 dégâts de moins.",
  Retraite:
    "Ramener ton Actif sur le banc et le remplacer par un Pokémon du banc. Ça coûte des énergies, une seule fois par tour.",
  Stade:
    "Une carte Dresseur posée sur le côté, qui change la règle pour les deux joueurs. Un seul en jeu à la fois.",
  Supporter: "Une carte Dresseur puissante : une seule par tour.",
  Talent: "Un pouvoir écrit sur une carte Pokémon, qui s'utilise sans attaquer.",
  Tour: "Ton passage. Il va de ta pioche à ton attaque, puis c'est à l'adversaire.",
  "Zone perdue":
    "Une zone à part, visible de tous : une carte qui y va ne revient jamais dans la partie.",
};

/**
 * Trouve l'identifiant de règle dans un texte de refus.
 *
 * Deux refus arrivent au client sous deux formes, et c'est le serveur qui en décide :
 * `vue.actions_refusees[]` porte `regle` et `message` **séparés** (grisage préventif), tandis qu'un
 * coup soumis puis refusé revient en HTTP 422 avec un `detail` où le moteur a fondu les deux en une
 * chaîne — « … (R-9.2) ». Cette fonction récupère la règle dans le second cas, pour que l'écran
 * explique un coup refusé comme il explique un coup grisé.
 *
 * Rend `null` quand aucun identifiant n'apparaît : on ne devine pas une règle, on n'affiche alors
 * que le message du serveur (pas de repli silencieux sur une explication au hasard).
 */
export function regleDuRefus(texte: string | null | undefined): string | null {
  if (!texte) return null;
  const trouve = texte.match(/R-\d+\.\d+/);
  return trouve ? trouve[0] : null;
}

/** Un refus mis en mots pour le joueur : la raison du serveur, plus la règle expliquée. */
export type RefusExplique = {
  /** Le message **du moteur**, tel quel : le serveur fait autorité sur le *pourquoi* factuel. */
  message: string;
  /** L'identifiant de règle cité, s'il y en a un. */
  regle: string | null;
  /** L'explication de cette règle, absente quand la règle n'est pas citée ou pas connue. */
  explication: Explication | null;
};

/**
 * Met un refus en mots : le message du moteur, et l'explication de la règle qu'il cite.
 *
 * Accepte les deux formes de refus (`{regle, message}` du grisage, ou la chaîne `detail` d'un 422).
 * L'explication reste `null` si la règle est inconnue — l'écran montre alors le seul message du
 * serveur, jamais une explication inventée.
 */
export function expliquerRefus(
  refus: string | { regle?: string | null; message?: string | null },
): RefusExplique {
  const message = typeof refus === "string" ? refus : (refus.message ?? "");
  const brut = typeof refus === "string" ? refus : (refus.regle ?? "");
  const regle = regleDuRefus(brut) ?? regleDuRefus(message);
  return { message, regle, explication: regle ? (EXPLICATIONS[regle] ?? null) : null };
}

/**
 * Un coup proposé au joueur, **pour affichage seulement**.
 *
 * Il n'y a volontairement **pas** de `params` : cet objet ne suffit pas à soumettre un coup au
 * serveur, donc l'aide ne peut pas jouer à la place du joueur, même par accident d'un futur
 * appelant. C'est le troisième critère d'acceptation du lot, tenu par la structure des données.
 */
export type Suggestion = {
  /** Le type de coup (`attacher_energie`, `declarer_attaque`…), pour choisir une icône. */
  type: string;
  /** L'étiquette **du serveur** : le libellé exact du coup tel qu'il est proposé dans la barre. */
  etiquette: string;
  /** Pourquoi c'est un bon coup à regarder maintenant, en une phrase d'enfant. */
  pourquoi: string;
};

/**
 * L'ordre dans lequel on *montre* les coups à qui débute, du plus urgent au plus accessoire.
 *
 * Ce n'est pas l'ordre des règles mais un ordre **pédagogique** : ce qu'un joueur doit régler avant
 * tout (une décision qui bloque la partie, une pioche obligatoire) passe devant ce qui est
 * optionnel. Un type absent de cette table est proposé en dernier — on ne le cache pas.
 */
const ORDRE_PEDAGOGIQUE: readonly string[] = [
  "placer_mise_en_place",
  "promouvoir",
  "repondre_demande",
  "piocher",
  "poser",
  "attacher_energie",
  "evoluer",
  "attacher_outil",
  "jouer_objet",
  "jouer_supporter",
  "jouer_stade",
  "activer_talent",
  "retraite",
  "declarer_attaque",
  "avancer_phase",
  "fin_tour",
];

/**
 * Les coups qu'on ne **propose** jamais, même quand ils sont légaux.
 *
 * `abandonner` est légal à tout instant (R-14.3) et resterait donc en tête de n'importe quelle
 * liste de coups possibles. Suggérer à un enfant d'abandonner quand il hésite serait le contraire
 * de l'aide. Le bouton existe toujours dans la barre d'actions : on ne le cache pas, on ne le
 * recommande pas.
 */
const JAMAIS_SUGGERE: readonly string[] = ["abandonner", "deserter"];

/** Pourquoi regarder tel coup — une phrase par type de coup, sinon un repli volontairement neutre. */
const POURQUOI: Record<string, string> = {
  placer_mise_en_place: "La partie attend que tu poses ton premier Pokémon.",
  promouvoir: "Ton Actif est tombé : choisis qui prend sa place, la partie attend.",
  repondre_demande: "Une carte te pose une question : réponds-y pour continuer.",
  piocher: "C'est le début de ton tour : commence par piocher.",
  poser: "Plus tu as de Pokémon sur ton banc, moins un K.O. te fait mal.",
  attacher_energie: "Sans énergie, ton Actif ne peut pas attaquer. Tu as droit à une par tour.",
  evoluer: "Faire évoluer rend ton Pokémon plus fort, et il garde tout ce qu'il portait.",
  attacher_outil: "Un Outil améliore un Pokémon pour tout le reste de la partie.",
  jouer_objet: "Les Objets ne coûtent rien et tu peux en jouer autant que tu veux.",
  jouer_supporter: "Un Supporter est puissant, mais tu n'en as qu'un par tour.",
  jouer_stade: "Un Stade change la règle pour vous deux.",
  activer_talent: "Un talent s'utilise sans attaquer : c'est du bonus.",
  retraite: "Si ton Actif est en danger, échange-le contre un Pokémon du banc.",
  declarer_attaque: "C'est le coup qui fait gagner — mais il termine ton tour.",
  avancer_phase: "Tu as fini ? Passe à la suite.",
  fin_tour: "Tu as fini ? Passe la main à l'adversaire.",
};

/**
 * Les coups à montrer au joueur qui hésite, ordonnés et mis en mots.
 *
 * Source **unique** : `vue.actions_legales`, que le serveur a calculées. L'aide ne redérive aucune
 * légalité — elle trie et met en phrase. Une vue sans `actions_legales` (plateau en lecture seule,
 * ou vue d'avant le lot `j-plateau-interactions`) rend une liste vide, jamais une erreur.
 *
 * @param vue la vue projetée pour ce joueur
 * @param maximum combien de coups au plus (par défaut 3 : au-delà, ce n'est plus une aide)
 */
export function suggestions(vue: VuePartie, maximum = 3): Suggestion[] {
  const legales = vue.actions_legales ?? [];
  const rang = (type: string) => {
    const i = ORDRE_PEDAGOGIQUE.indexOf(type);
    return i === -1 ? ORDRE_PEDAGOGIQUE.length : i;
  };
  return legales
    .filter((a) => !JAMAIS_SUGGERE.includes(a.type))
    .slice() // ne jamais trier la liste du serveur en place
    .sort((a, b) => rang(a.type) - rang(b.type))
    .slice(0, Math.max(0, maximum))
    .map((a) => ({
      type: a.type,
      etiquette: a.etiquette,
      pourquoi: POURQUOI[a.type] ?? "Un coup possible en ce moment.",
    }));
}

/**
 * Les mots du {@link GLOSSAIRE} présents dans un texte, pour les proposer en lecture à côté.
 *
 * Comparaison insensible à la casse sur le mot entier (pas de sous-chaîne : « Objet » ne doit pas
 * se déclencher sur « objectif »). Rendus dans l'ordre du glossaire, pour un affichage stable.
 */
export function motsDuTexte(texte: string): string[] {
  return Object.keys(GLOSSAIRE).filter((mot) => {
    const echappe = mot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|[^\\p{L}])${echappe}([^\\p{L}]|$)`, "iu").test(texte);
  });
}
