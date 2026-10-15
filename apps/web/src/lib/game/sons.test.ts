import { describe, expect, it } from "vitest";

import { TYPES_EVENEMENT_CONNUS } from "./journal";
import { SPECS, type Typage } from "./anim-types";
import {
  CLE_SONS,
  DUREE_COUP_MAX,
  DUREE_SON_MAX,
  ECART_MIN,
  FILE_SONS_VIDE,
  GAIN_MAX,
  MUSIQUE,
  SEUIL_MINUTERIE_MS,
  SEUIL_RATTRAPAGE_SONS,
  SONS,
  SONS_DEFAUT,
  SONS_PAR_EVENEMENT,
  TIMBRES_TYPE,
  type CoupSons,
  bornerGain,
  dureeBoucleMusique,
  issueFin,
  normaliserSons,
  planifierSons,
  reduireSons,
  sonAttaque,
  sonImpact,
  tirerSon,
} from "./sons";

/**
 * Les sons du jeu (lot `j-son`) — la banque, les volumes relatifs, la file. **Pur** : aucun
 * navigateur, aucun `AudioContext`, aucun fichier audio. La CI fait foi.
 *
 * Ces tests portent les trois critères d'acceptation du lot, et le risque qu'il nomme :
 *
 * 1. **tous les sons sont libres de droits, et leur origine est écrite dans le dépôt** — ici en
 *    prouvant qu'il n'existe *aucune* source externe : chaque son est une recette de ce fichier,
 *    renderable par le navigateur, sans URL ni octet importé. La garde correspondante côté dépôt
 *    (aucun fichier audio dans `public/`) est dans `src/__tests__/sons-origine-garde.test.ts` ;
 * 2. **la coupure est immédiate et mémorisée** — ici côté file (couper vide et mémorise, de sorte
 *    qu'un rétablissement ne déverse pas l'arriéré), et côté écran dans
 *    `src/__tests__/sons-provider.test.tsx` ;
 * 3. **aucun son avant une interaction du joueur** — c'est une propriété du navigateur, donc
 *    testée là où l'`AudioContext` est créé : `src/__tests__/sons-provider.test.tsx`.
 *
 * Et le point que le lot exige nommément : *« aucun son ne surprenne, la minuterie surtout »*.
 */

/** Un coup minimal, pour ne pas répéter la forme à chaque test. */
function coup(numero: number, evenements: { type: string; donnees?: Record<string, unknown> }[]): CoupSons {
  return { numero, evenements };
}

/** Le premier élément d'une liste, ou un échec bruyant : une recette sans partiel serait un bug. */
function premier<T>(xs: readonly T[]): T {
  const x = xs[0];
  if (x === undefined) throw new Error("liste vide là où le test en attend un élément");
  return x;
}

/** Un typage complet, à partir de ce qui nous intéresse dans le cas testé. */
function typage(partiel: Partial<Typage>): Typage {
  return { type: "", degats: 0, faiblesse: false, resistance: false, echec: false, ...partiel };
}

describe("banque de sons — origine et innocuité", () => {
  it("décrit chaque son entièrement en données : aucune URL, aucun fichier, donc aucune licence", () => {
    // Le risque du lot est un risque de DROITS. La parade n'est pas une liste de crédits qu'il
    // faudrait tenir à jour : c'est qu'il n'y ait rien à créditer. Une recette ne contient que des
    // nombres et des formes d'onde — s'y glisser une chaîne qui ressemble à un chemin ou à une URL
    // serait réintroduire exactement le risque qu'on a supprimé.
    const serialise = JSON.stringify(SONS);
    expect(serialise).not.toMatch(/https?:\/\//);
    expect(serialise).not.toMatch(/\.(mp3|ogg|wav|m4a|aac|flac|webm)/i);
    expect(Object.keys(SONS).length).toBeGreaterThanOrEqual(17);
  });

  it("borne chaque recette : durée, gain, et une enveloppe qui ne claque jamais", () => {
    for (const [cle, r] of Object.entries(SONS)) {
      expect(r.duree, `${cle} : durée`).toBeGreaterThan(0);
      expect(r.duree, `${cle} : durée`).toBeLessThanOrEqual(DUREE_SON_MAX);
      expect(r.gain, `${cle} : gain`).toBeGreaterThan(0);
      expect(r.gain, `${cle} : gain`).toBeLessThanOrEqual(GAIN_MAX);
      // Une montée nulle produit un claquement ("clic" numérique) : c'est le défaut le plus
      // désagréable d'un son synthétisé, et il est invisible à la lecture du code.
      expect(r.attaque, `${cle} : montée`).toBeGreaterThan(0);
      expect(r.chute, `${cle} : descente`).toBeGreaterThan(0);
      expect(r.attaque + r.chute, `${cle} : enveloppe plus longue que le son`).toBeLessThanOrEqual(r.duree);
      expect(r.passeBas, `${cle} : passe-bas`).toBeGreaterThan(0);
      expect(r.partiels.length, `${cle} : partiels`).toBeGreaterThan(0);
      const poids = r.partiels.reduce((s, p) => s + p.poids, 0);
      expect(poids, `${cle} : somme des poids`).toBeLessThanOrEqual(1.0001);
      for (const p of r.partiels) {
        expect(p.poids, `${cle} : poids d'un partiel`).toBeGreaterThan(0);
        expect(p.retard, `${cle} : retard`).toBeGreaterThanOrEqual(0);
        expect(p.retard, `${cle} : un partiel démarre après la fin du son`).toBeLessThan(r.duree);
      }
    }
  });

  it("garde les sons de coup courts : seule la fin de partie a le droit de durer", () => {
    // Un bruitage de coup qui dure une seconde se superpose au suivant et brouille la lecture du
    // plateau. La fin de partie, elle, ne se superpose à rien — la partie est finie.
    const finDePartie = new Set(["victoire", "defaite", "egalite"]);
    for (const [cle, r] of Object.entries(SONS)) {
      if (finDePartie.has(cle)) continue;
      expect(r.duree, `${cle} : un son de coup ne doit pas dépasser ${DUREE_COUP_MAX} ms`).toBeLessThanOrEqual(
        DUREE_COUP_MAX,
      );
    }
  });

  it("fait de la minuterie le son STRICTEMENT le plus discret de la banque", () => {
    // Exigence nommée du lot : « qu'aucun son ne surprenne (la minuterie surtout) ». Elle est ici,
    // en garde, et pas seulement dans un commentaire : baisser un autre son sous celui-ci — ou
    // monter la minuterie — casse la CI et nomme le fautif.
    const autres = Object.entries(SONS).filter(([cle]) => cle !== "minuterie");
    for (const [cle, r] of autres) {
      expect(r.gain, `${cle} doit rester plus fort que la minuterie`).toBeGreaterThan(SONS.minuterie.gain);
    }
  });

  it("garde la musique d'ambiance sous la minuterie : un fond qui s'entend n'est plus un fond", () => {
    expect(MUSIQUE.gain).toBeLessThan(SONS.minuterie.gain);
    expect(MUSIQUE.notes.length).toBeGreaterThan(0);
    expect(dureeBoucleMusique()).toBe(MUSIQUE.notes.length * MUSIQUE.ecart + MUSIQUE.duree);
    // Une boucle trop courte s'entend comme une boucle : on la veut au-delà de cinq secondes.
    expect(dureeBoucleMusique()).toBeGreaterThan(5_000);
  });
});

describe("parité des registres — une faute de frappe ne peut pas devenir un silence", () => {
  it("n'associe de son qu'à des événements que le serveur émet réellement", () => {
    // La pire panne de ce lot serait un son qui ne se déclenche jamais : le silence est une sortie
    // plausible, donc personne ne le signale. Cette garde la rend impossible.
    const connus = new Set(TYPES_EVENEMENT_CONNUS);
    for (const type of Object.keys(SONS_PAR_EVENEMENT)) {
      expect(connus.has(type), `${type} n'est pas un type d'événement connu du serveur`).toBe(true);
    }
  });

  it("ne renvoie que vers des clés qui existent dans la banque", () => {
    for (const [type, cle] of Object.entries(SONS_PAR_EVENEMENT)) {
      expect(SONS[cle], `${type} renvoie vers un son inexistant : ${cle}`).toBeDefined();
    }
  });

  it("donne un timbre à CHAQUE type d'énergie que l'effet visuel connaît", () => {
    // Si l'image montre un effet typé et que le son reste neutre, les deux racontent deux choses
    // différentes. Un douzième type ajouté à `SPECS` sans timbre casse la CI ici.
    expect(Object.keys(TIMBRES_TYPE).sort()).toEqual(Object.keys(SPECS).sort());
  });

  it("borne chaque timbre dans l'audible, et garde une part de bruit crédible", () => {
    for (const [type, t] of Object.entries(TIMBRES_TYPE)) {
      for (const f of [t.depart, t.arrivee]) {
        expect(f, `${type} : fréquence`).toBeGreaterThan(20);
        expect(f, `${type} : fréquence`).toBeLessThan(16_000);
      }
      expect(t.bruit, `${type} : bruit`).toBeGreaterThanOrEqual(0);
      expect(t.bruit, `${type} : bruit`).toBeLessThan(1);
    }
  });
});

describe("sonImpact / sonAttaque — le son dit ce que l'image dit", () => {
  it("retimbre l'IMPACT selon le type d'énergie du serveur", () => {
    const feu = sonImpact(typage({ type: "fire", degats: 60 }));
    const eclair = sonImpact(typage({ type: "lightning", degats: 60 }));
    expect(premier(feu.partiels).forme).toBe(TIMBRES_TYPE.fire.forme);
    expect(premier(eclair.partiels).forme).toBe(TIMBRES_TYPE.lightning.forme);
    expect(premier(feu.partiels).depart).not.toBe(premier(eclair.partiels).depart);
    expect(feu.libelle).toContain("Feu");
  });

  it("tire l'intensité du résultat réel : un gros coup sonne plus fort qu'un petit", () => {
    const petit = sonImpact(typage({ type: "water", degats: 10 }));
    const gros = sonImpact(typage({ type: "water", degats: 200 }));
    expect(gros.gain).toBeGreaterThan(petit.gain);
    // Et un petit coup reste AUDIBLE : un son qui tombe à zéro ferait croire que rien n'est parti.
    expect(petit.gain).toBeGreaterThan(0);
    expect(gros.gain).toBeLessThanOrEqual(GAIN_MAX);
  });

  it("joue le son d'échec quand l'attaque a raté, pas un son d'attaque ordinaire", () => {
    expect(sonAttaque(typage({ type: "fire", echec: true }))).toBe(SONS.echec);
    // Une attaque qui part normalement reste NEUTRE : c'est l'impact qui portera le type.
    expect(sonAttaque(typage({ type: "fire", degats: 60 }))).toBe(SONS.attaque);
    expect(sonAttaque(null)).toBe(SONS.attaque);
  });

  it("garde la recette de base quand le serveur ne donne pas de type (D9 : on n'invente pas)", () => {
    expect(sonImpact(null)).toBe(SONS.impact);
    expect(sonImpact(typage({ type: "" }))).toBe(SONS.impact);
    expect(sonImpact(typage({ type: "un_type_inconnu" }))).toBe(SONS.impact);
  });
});

describe("issueFin — le serveur dit qui gagne, on ne déduit rien d'autre", () => {
  it("distingue victoire, défaite et égalité du point de vue du destinataire", () => {
    expect(issueFin({ vainqueur: "j1" }, "j1")).toBe("victoire");
    expect(issueFin({ vainqueur: "j2" }, "j1")).toBe("defaite");
    expect(issueFin({ vainqueur: null }, "j1")).toBe("egalite");
    expect(issueFin({}, "j1")).toBe("egalite");
  });
});

describe("planifierSons — le son et l'image viennent du même événement", () => {
  it("planifie un son par événement sonore, dans l'ordre des coups", () => {
    const sons = planifierSons(
      [
        coup(2, [{ type: "pokemon_pose", donnees: { joueur: "j1" } }]),
        coup(1, [{ type: "cartes_piochees", donnees: { joueur: "j1" } }]),
      ],
      "j1",
    );
    expect(sons.map((s) => s.son)).toEqual(["pioche", "pose"]);
  });

  it("ne produit RIEN pour un événement délibérément muet, et ne bloque pas la suite", () => {
    const sons = planifierSons(
      [
        coup(1, [
          { type: "etat_checkup", donnees: { joueur: "j1" } },
          { type: "pokemon_pose", donnees: { joueur: "j1" } },
        ]),
      ],
      "j1",
    );
    expect(sons.map((s) => s.son)).toEqual(["pose"]);
  });

  it("découpe un K.O. avec récompenses en DEUX sons : la chute, puis les cartes prises", () => {
    // Le serveur envoie les deux sur un seul événement. Les fondre en un bruit ferait disparaître
    // l'information la plus importante de la partie — le compte des récompenses.
    const sons = planifierSons(
      [coup(1, [{ type: "ko", donnees: { joueur: "j2", par: "j1", recompenses_prises: 2 } }])],
      "j1",
    );
    expect(sons.map((s) => s.son)).toEqual(["ko", "recompense"]);
    // Deux clés distinctes, sinon la mémoire anti-doublon en avalerait une.
    expect(new Set(sons.map((s) => s.cle)).size).toBe(2);
  });

  it("ne sonne pas la récompense quand le K.O. n'en fait prendre aucune", () => {
    const sons = planifierSons([coup(1, [{ type: "ko", donnees: { joueur: "j2" } }])], "j1");
    expect(sons.map((s) => s.son)).toEqual(["ko"]);
  });

  it("sonne la victoire pour le gagnant et la défaite pour l'autre, sur le MÊME coup", () => {
    const evenements = [{ type: "partie_terminee", donnees: { vainqueur: "j1", raison: "recompenses" } }];
    expect(planifierSons([coup(9, evenements)], "j1").map((s) => s.son)).toEqual(["victoire"]);
    expect(planifierSons([coup(9, evenements)], "j2").map((s) => s.son)).toEqual(["defaite"]);
  });

  it("retimbre l'impact depuis le typage que le plan d'animation a calculé", () => {
    // C'est ce test qui a trouvé le défaut : le socle ne typpe `attaque_declaree` QUE sur un échec,
    // donc un timbre posé là serait resté muet sur toutes les attaques qui portent. Le type vit sur
    // `degats`, lu sur le COUP entier — le son le prend exactement là. Si les deux lectures
    // divergeaient un jour, ce test tomberait.
    const sons = planifierSons(
      [
        coup(1, [
          { type: "degats", donnees: { cible: "p2", degats: 120 } },
          { type: "attaque_declaree", donnees: { joueur: "j1", type: "lightning" } },
        ]),
      ],
      "j1",
    );
    const impact = sons.find((s) => s.son === "impact");
    expect(impact).toBeDefined();
    expect(premier(impact?.recette.partiels ?? []).forme).toBe(TIMBRES_TYPE.lightning.forme);
    // L'attaque déclarée, elle, reste le geste neutre.
    expect(sons.find((s) => s.son === "attaque")?.recette).toBe(SONS.attaque);
  });

  it("joue le son d'échec, et AUCUN impact, quand l'attaque a raté au pile ou face", () => {
    const sons = planifierSons(
      [
        coup(1, [
          { type: "attaque_declaree", donnees: { joueur: "j1", type: "fire" } },
          { type: "dsl_pile_ou_face", donnees: { joueur: "j1", pieces: 1, faces: 0 } },
        ]),
      ],
      "j1",
    );
    expect(sons.map((s) => s.son)).toEqual(["echec", "piece"]);
  });

  it("tolère un coup sans événements et un événement sans données", () => {
    expect(planifierSons([coup(1, [])], "j1")).toEqual([]);
    expect(planifierSons([coup(1, [{ type: "pokemon_pose" }])], "j1").map((s) => s.son)).toEqual(["pose"]);
  });
});

describe("la file de sons", () => {
  it("ne rejoue jamais un son déjà entendu, même si la resynchronisation recouvre", () => {
    const sons = planifierSons([coup(1, [{ type: "pokemon_pose" }])], "j1");
    let file = reduireSons(FILE_SONS_VIDE, { type: "empiler", sons });
    const tir = tirerSon(file, 1_000);
    expect(tir.son?.son).toBe("pose");
    file = tir.file;
    // La même resync arrive de nouveau (F5, reconnexion) : rien ne doit sonner.
    file = reduireSons(file, { type: "empiler", sons });
    expect(file.attente).toHaveLength(0);
    expect(tirerSon(file, 5_000).son).toBeNull();
  });

  it("interdit deux départs à moins de l'écart minimum : une rafale n'est pas un bourdonnement", () => {
    const sons = planifierSons(
      [coup(1, [{ type: "pokemon_pose" }, { type: "energie_attachee" }])],
      "j1",
    );
    let file = reduireSons(FILE_SONS_VIDE, { type: "empiler", sons });
    const premier = tirerSon(file, 1_000);
    expect(premier.son).not.toBeNull();
    file = premier.file;
    // Tout de suite après : refusé, et le son reste EN ATTENTE (il n'est pas jeté).
    const trop = tirerSon(file, 1_000 + ECART_MIN - 1);
    expect(trop.son).toBeNull();
    expect(trop.file.attente).toHaveLength(1);
    // L'écart écoulé : il sort.
    const apres = tirerSon(file, 1_000 + ECART_MIN);
    expect(apres.son?.son).toBe("energie");
  });

  it("ne joue qu'UN son après une reprise, et COMPTE ceux qu'il n'a pas joués", () => {
    // Vingt événements arrivent d'un bloc (reconnexion) : vingt sons d'affilée seraient du bruit.
    // On garde le dernier — celui qui explique la situation présente.
    const evenements = Array.from({ length: 20 }, () => ({ type: "cartes_piochees" as const }));
    const sons = planifierSons([coup(1, evenements)], "j1");
    expect(sons).toHaveLength(20);
    const file = reduireSons(FILE_SONS_VIDE, { type: "empiler", sons });
    expect(file.attente).toHaveLength(1);
    expect(file.ignores).toBe(19);
    // Rien n'est perdu en silence : le compte est exposé, et le journal porte chaque phrase.
    expect(premier(file.attente).cle).toBe(sons[sons.length - 1]?.cle);
  });

  it("laisse passer une rafale courte sans la rattraper", () => {
    const evenements = Array.from({ length: SEUIL_RATTRAPAGE_SONS }, () => ({ type: "cartes_piochees" as const }));
    const file = reduireSons(FILE_SONS_VIDE, { type: "empiler", sons: planifierSons([coup(1, evenements)], "j1") });
    expect(file.attente).toHaveLength(SEUIL_RATTRAPAGE_SONS);
    expect(file.ignores).toBe(0);
  });

  it("coupe IMMÉDIATEMENT, et un rétablissement ne déverse pas l'arriéré", () => {
    const sons = planifierSons(
      [coup(1, [{ type: "pokemon_pose" }, { type: "energie_attachee" }, { type: "talent_active" }])],
      "j1",
    );
    let file = reduireSons(FILE_SONS_VIDE, { type: "empiler", sons });
    expect(file.attente.length).toBeGreaterThan(0);
    file = reduireSons(file, { type: "couper" });
    expect(file.attente).toHaveLength(0);
    expect(tirerSon(file, 10_000).son).toBeNull();
    // Ce qui était en attente est MÉMORISÉ : on rétablit, la même resync n'en rejoue aucun.
    file = reduireSons(file, { type: "empiler", sons });
    expect(file.attente).toHaveLength(0);
  });

  it("repart d'une file neuve quand on change de partie", () => {
    const sons = planifierSons([coup(1, [{ type: "pokemon_pose" }])], "j1");
    let file = reduireSons(FILE_SONS_VIDE, { type: "empiler", sons });
    file = tirerSon(file, 1_000).file;
    file = reduireSons(file, { type: "reinitialiser" });
    expect(file).toEqual(FILE_SONS_VIDE);
    // Les numéros de coup d'une autre partie n'ont rien à voir : le même plan doit resonner.
    file = reduireSons(file, { type: "empiler", sons });
    expect(tirerSon(file, 1_000).son?.son).toBe("pose");
  });

  it("reste au repos sur une file vide, sans jamais lever", () => {
    expect(tirerSon(FILE_SONS_VIDE, 0)).toEqual({ file: FILE_SONS_VIDE, son: null });
    expect(reduireSons(FILE_SONS_VIDE, { type: "empiler", sons: [] })).toBe(FILE_SONS_VIDE);
  });

  it("borne sa mémoire : une partie longue ne fait pas enfler la file", () => {
    let file = FILE_SONS_VIDE;
    for (let n = 1; n <= 400; n += 1) {
      file = reduireSons(file, { type: "empiler", sons: planifierSons([coup(n, [{ type: "pokemon_pose" }])], "j1") });
      file = tirerSon(file, n * 1_000).file;
    }
    expect(file.vues.length).toBeLessThanOrEqual(300);
  });
});

describe("réglages par appareil (DJ9)", () => {
  it("applique la décision DJ9 à la lettre : bruitages activés, musique coupée", () => {
    expect(SONS_DEFAUT.bruitages).toBe(true);
    expect(SONS_DEFAUT.musique).toBe(false);
  });

  it("laisse de la marge vers le haut : un réglage qui ne peut que baisser s'entend comme une panne", () => {
    expect(SONS_DEFAUT.volume).toBeGreaterThan(0);
    expect(SONS_DEFAUT.volume).toBeLessThan(1);
  });

  it("range le réglage sous une clé par APPAREIL, distincte du confort du compte", () => {
    expect(CLE_SONS).toBe("pbm.jeu.sons");
  });

  it("normalise champ par champ, jamais en bloc", () => {
    expect(normaliserSons({ bruitages: false })).toEqual({
      bruitages: false,
      musique: SONS_DEFAUT.musique,
      volume: SONS_DEFAUT.volume,
    });
    expect(normaliserSons(null)).toEqual(SONS_DEFAUT);
    expect(normaliserSons("n'importe quoi")).toEqual(SONS_DEFAUT);
    expect(normaliserSons({ volume: "fort" })).toEqual(SONS_DEFAUT);
  });

  it("borne le volume dans [0, 1] plutôt que de faire confiance au stockage local", () => {
    expect(normaliserSons({ volume: 12 }).volume).toBe(1);
    expect(normaliserSons({ volume: -3 }).volume).toBe(0);
    expect(normaliserSons({ volume: Number.NaN }).volume).toBe(SONS_DEFAUT.volume);
  });

  it("borne un gain hors limites plutôt que de saturer la sortie", () => {
    expect(bornerGain(10)).toBe(GAIN_MAX);
    expect(bornerGain(0)).toBe(0);
    expect(bornerGain(-1)).toBe(0);
    expect(bornerGain(Number.NaN)).toBe(0);
  });

  it("laisse à la minuterie le temps d'être utile : dix secondes, pas deux", () => {
    expect(SEUIL_MINUTERIE_MS).toBeGreaterThanOrEqual(5_000);
  });
});
