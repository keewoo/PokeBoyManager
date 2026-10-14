import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  COMPRESSION_MIN,
  COUCHES_UTILISEES,
  DUREE_REDUITE_MOMENT,
  FILE_MOMENTS_VIDE,
  GENRES_MOMENT,
  MOMENTS,
  MOMENT_MAX_MS,
  OBJETS_MAX,
  type EffetMoment,
  type GenreMoment,
  type MomentPlanifie,
  badgeMoment,
  effetMoment,
  facteurCompression,
  momentsEvenement,
  phraseMoment,
  planifierMoments,
  reduireMoments,
} from "@/lib/game/anim-moments";

/**
 * Les six moments clés (lot `j-anim-evolution-ko`), et surtout ses **trois critères
 * d'acceptation** — chacun a ici son bloc nommé, parce qu'un critère vérifié par un test qu'on ne
 * retrouve pas est un critère qu'on cassera sans le voir.
 */

/** Un événement brut, dans la forme tolérante du temps réel. */
const evt = (type: string, donnees: Record<string, unknown> = {}) => ({ type, donnees });

/** Le coup qui porte ces événements. */
const coup = (numero: number, evenements: unknown[]) => ({ numero, evenements });

/** Joue une file jusqu'à épuisement, en relevant chaque moment courant dans l'ordre. */
function deroulerFile(moments: MomentPlanifie[]): { ordre: string[]; simultanes: number } {
  let file = reduireMoments(FILE_MOMENTS_VIDE, { type: "empiler", moments });
  const ordre: string[] = [];
  let simultanes = 0;
  // Borne de sécurité : une file qui ne se vide pas est un bug, pas une boucle infinie de test.
  for (let i = 0; i < 100 && file.courant; i += 1) {
    ordre.push(file.courant.cle);
    // L'invariant du critère n°1 : jamais deux moments « en cours ». `courant` est un objet ou
    // `null`, donc le compter suffit — mais on le compte explicitement pour que l'échec le dise.
    simultanes = Math.max(simultanes, file.courant ? 1 : 0);
    file = reduireMoments(file, { type: "avancer" });
  }
  return { ordre, simultanes };
}

describe("anim-moments — la table des six moments", () => {
  it("couvre exactement les six genres du lot", () => {
    expect([...GENRES_MOMENT].sort()).toEqual(
      ["evolution", "ko", "mise-en-place", "mulligan", "piece", "recompense"].sort(),
    );
  });

  it.each(GENRES_MOMENT)(
    "%s ne dure jamais plus d'une seconde et demie (le risque nommé par le lot)",
    (genre) => {
      // « Faire durer l'animation de K.O. plus que le plaisir : au-delà d'une seconde et demie,
      // elle agace au lieu de marquer. » La borne vaut pour les six, pas seulement pour le K.O. :
      // c'est ce qui la rendra encore vraie quand un septième genre arrivera.
      expect(MOMENTS[genre].duree).toBeLessThanOrEqual(MOMENT_MAX_MS);
      expect(effetMoment({ ...moment(genre) }).duree).toBeLessThanOrEqual(MOMENT_MAX_MS);
    },
  );

  it.each(GENRES_MOMENT)("%s a au moins deux temps, tous de poids strictement positif", (genre) => {
    const phases = MOMENTS[genre].phases;
    expect(phases.length).toBeGreaterThanOrEqual(2);
    for (const p of phases) expect(p.poids).toBeGreaterThan(0);
  });

  it("n'utilise que les six couches déclarées (pas de couche orpheline dans la table)", () => {
    const connues = new Set(["halo", "fondu", "voile", "traine", "eclat", "rotation"]);
    for (const c of COUCHES_UTILISEES) expect(connues, `couche inconnue : ${c}`).toContain(c);
  });

  it("le pile ou face est le seul genre qui fait tourner quelque chose", () => {
    // Si un autre genre gagnait un temps nommé `rotation`, il hériterait de la mécanique de
    // révélation différée sans l'avoir demandée — et `revelationA` cesserait de vouloir dire
    // « le résultat n'est pas encore montré ».
    const avecRotation = GENRES_MOMENT.filter((g) =>
      MOMENTS[g].phases.some((p) => p.nom === "rotation"),
    );
    expect(avecRotation).toEqual(["piece"]);
  });
});

/** Un moment planifié minimal du genre demandé, pour les tests de composition. */
function moment(genre: GenreMoment, patch: Partial<MomentPlanifie> = {}): MomentPlanifie {
  return {
    cle: `1:0:${genre}`,
    genre,
    numero: 1,
    rang: 0,
    cible: null,
    camp: "moi",
    objets: genre === "piece" ? 2 : 2,
    piece: genre === "piece" ? { pieces: 2, faces: 1 } : null,
    detail: null,
    ...patch,
  };
}

describe("anim-moments — ce que les événements du serveur produisent", () => {
  it("une évolution montre la pile : deux cartes, et le nom quand le serveur le donne", () => {
    const [m] = momentsEvenement(
      evt("evolution", { joueur: "a", base: "i-1", nom: "Herbizarre" }),
      3,
      1,
      "a",
    );
    expect(m).toMatchObject({
      genre: "evolution",
      cible: "i-1",
      camp: "moi",
      objets: 2,
      detail: "Herbizarre",
      cle: "3:1:evolution",
    });
  });

  it("un K.O. avec récompenses produit DEUX moments — le serveur ne les sépare pas", () => {
    // `recompenses_prises` voyage sur l'événement `ko` : sans cette séparation, la prise de
    // récompense n'aurait aucune animation, alors que le lot l'exige explicitement.
    const ms = momentsEvenement(
      evt("ko", { joueur: "b", pokemon: "i-9", recompenses_prises: 2, par: "a" }),
      4,
      2,
      "a",
    );
    expect(ms.map((m) => m.genre)).toEqual(["ko", "recompense"]);
    expect(ms[0]).toMatchObject({ cible: "i-9", camp: "adversaire", objets: 1 });
    // La récompense profite à `par`, pas au propriétaire du Pokémon tombé : teinter du camp du
    // perdant dirait le contraire de ce qui se passe à l'écran.
    expect(ms[1]).toMatchObject({ camp: "moi", objets: 2, cible: null });
    expect(new Set(ms.map((m) => m.cle)).size).toBe(2);
  });

  it("un K.O. sans récompense (R-13.1 sans prise) ne produit que le K.O.", () => {
    const ms = momentsEvenement(
      evt("ko", { joueur: "b", pokemon: "i-9", recompenses_prises: 0, par: "a" }),
      4,
      2,
      "a",
    );
    expect(ms.map((m) => m.genre)).toEqual(["ko"]);
  });

  it("la révélation simultanée n'appartient à personne (R-4.2/R-4.3)", () => {
    const [m] = momentsEvenement(
      evt("mise_en_place_revelee", {
        joueurs: [
          { joueur: "a", recompenses_nombre: 6 },
          { joueur: "b", recompenses_nombre: 6 },
        ],
      }),
      1,
      0,
      "a",
    );
    expect(m).toMatchObject({ genre: "mise-en-place", camp: "auto", objets: 6 });
  });

  it("un mulligan montre autant de cartes que la main révélée (R-4.4)", () => {
    const cartes = Array.from({ length: 7 }, (_, i) => ({ ref: `r-${i}` }));
    const [m] = momentsEvenement(evt("main_revelee", { joueur: "a", cartes }), 1, 0, "a");
    expect(m).toMatchObject({ genre: "mulligan", objets: 7, camp: "moi" });
  });

  it("une main plus grande que le plafond est bornée, jamais rendue à l'identique", () => {
    const cartes = Array.from({ length: 30 }, (_, i) => ({ ref: `r-${i}` }));
    const [m] = momentsEvenement(evt("main_revelee", { joueur: "a", cartes }), 1, 0, "a");
    expect(m?.objets).toBe(OBJETS_MAX);
  });

  it("un pile ou face porte le compte du serveur, borné par le nombre de pièces", () => {
    const [m] = momentsEvenement(evt("dsl_pile_ou_face", { pieces: 2, faces: 1 }), 5, 0, "a");
    expect(m).toMatchObject({ genre: "piece", objets: 2, piece: { pieces: 2, faces: 1 } });
    // Un `faces` aberrant (plus de faces que de pièces) est ramené, pas rendu tel quel : l'écran
    // ne doit pas pouvoir montrer trois faces sur deux pièces.
    const [aberrant] = momentsEvenement(evt("dsl_pile_ou_face", { pieces: 2, faces: 9 }), 5, 0, "a");
    expect(aberrant?.piece).toEqual({ pieces: 2, faces: 2 });
  });

  it("zéro pièce lancée ne montre aucune pièce (pas de lancer fantôme)", () => {
    expect(momentsEvenement(evt("dsl_pile_ou_face", { pieces: 0, faces: 0 }), 5, 0, "a")).toEqual([]);
  });

  it("une Confusion est une pièce unique, pile quand l'attaque est annulée (R-11.5)", () => {
    const [annulee] = momentsEvenement(
      evt("confusion_resolue", { joueur: "a", attaque_annulee: true }),
      6,
      0,
      "a",
    );
    expect(annulee?.piece).toEqual({ pieces: 1, faces: 0 });
    const [passee] = momentsEvenement(
      evt("confusion_resolue", { joueur: "a", attaque_annulee: false }),
      6,
      0,
      "a",
    );
    expect(passee?.piece).toEqual({ pieces: 1, faces: 1 });
  });

  it("un événement qui n'est pas un moment clé n'en fabrique pas un", () => {
    // Un mélange de pioche se lit dans le journal. Lui donner un moment noierait les six qui
    // comptent — c'est le choix du lot, et il se garde.
    for (const type of ["pioche_melangee", "verrou_pose", "tour_commence", "", "inconnu"]) {
      expect(momentsEvenement(evt(type), 1, 0, "a"), type).toEqual([]);
    }
  });

  it("un événement malformé ne jette pas (le temps réel n'est pas typé)", () => {
    expect(momentsEvenement({ type: "ko" }, 1, 0, "a")).toHaveLength(1);
    expect(momentsEvenement({}, 1, 0, "a")).toEqual([]);
    expect(momentsEvenement({ type: "evolution", donnees: undefined }, 1, 0, "a")).toHaveLength(1);
  });

  it("les coups sont planifiés par numéro croissant, quel que soit l'ordre d'arrivée", () => {
    const ms = planifierMoments(
      [coup(7, [evt("evolution", { joueur: "a" })]), coup(3, [evt("ko", { joueur: "a" })])],
      "a",
    );
    expect(ms.map((m) => m.numero)).toEqual([3, 7]);
  });
});

describe("critère n°1 — un double K.O. affiche deux animations sans se chevaucher ni se perdre", () => {
  /** Le coup d'un double K.O. (R-13.5), chacun avec sa récompense. */
  const doubleKo = coup(12, [
    evt("ko", { joueur: "a", pokemon: "i-1", recompenses_prises: 1, par: "b" }),
    evt("degats", { cible: "i-2", degats: 60 }),
    evt("ko", { joueur: "b", pokemon: "i-2", recompenses_prises: 1, par: "a" }),
  ]);

  it("produit quatre moments distincts, dans l'ordre du coup", () => {
    const ms = planifierMoments([doubleKo], "a");
    expect(ms.map((m) => m.genre)).toEqual(["ko", "recompense", "ko", "recompense"]);
    // Les deux K.O. viennent du même coup : si la clé ne portait pas le rang de l'événement, le
    // second écraserait le premier à l'empilage et un K.O. disparaîtrait de l'écran.
    expect(new Set(ms.map((m) => m.cle)).size).toBe(4);
    expect(ms.map((m) => m.cle)).toEqual([
      "12:0:ko",
      "12:0:recompense",
      "12:2:ko",
      "12:2:recompense",
    ]);
  });

  it("les joue un par un, les quatre, sans jamais en avoir deux en cours", () => {
    const { ordre, simultanes } = deroulerFile(planifierMoments([doubleKo], "a"));
    expect(ordre).toEqual(["12:0:ko", "12:0:recompense", "12:2:ko", "12:2:recompense"]);
    expect(simultanes).toBe(1);
  });

  it("chaque K.O. garde son camp et sa carte : les deux ne se confondent pas", () => {
    const ms = planifierMoments([doubleKo], "a");
    const kos = ms.filter((m) => m.genre === "ko");
    expect(kos.map((m) => m.cible)).toEqual(["i-1", "i-2"]);
    expect(kos.map((m) => m.camp)).toEqual(["moi", "adversaire"]);
  });

  it("comprime la rafale au lieu d'en perdre un morceau", () => {
    const ms = planifierMoments([doubleKo], "a");
    const premier = effetMoment(ms[0] as MomentPlanifie, { enAttente: ms.length - 1 });
    const seul = effetMoment(ms[0] as MomentPlanifie, { enAttente: 0 });
    expect(premier.duree).toBeLessThan(seul.duree);
    // Comprimé, mais jamais effacé : un moment réduit à zéro serait un moment perdu.
    expect(premier.duree).toBeGreaterThanOrEqual(
      Math.floor(MOMENTS.ko.duree * COMPRESSION_MIN) - 1,
    );
    expect(premier.phases.every((p) => p.duree >= 0)).toBe(true);
    expect(premier.phases.reduce((s, p) => s + p.duree, 0)).toBe(premier.duree);
  });

  it("une resynchronisation qui recouvre ne rejoue pas les K.O. déjà vus", () => {
    const ms = planifierMoments([doubleKo], "a");
    let file = reduireMoments(FILE_MOMENTS_VIDE, { type: "empiler", moments: ms });
    file = reduireMoments(file, { type: "avancer" });
    // Le serveur rediffuse le même coup : aucun moment ne doit revenir, ni le courant ni les vus.
    const avant = file.attente.length;
    file = reduireMoments(file, { type: "empiler", moments: planifierMoments([doubleKo], "a") });
    expect(file.attente.length).toBe(avant);
  });

  it("une vidange mémorise ce qu'elle jette (le joueur agit, puis le serveur rediffuse)", () => {
    const ms = planifierMoments([doubleKo], "a");
    let file = reduireMoments(FILE_MOMENTS_VIDE, { type: "empiler", moments: ms });
    file = reduireMoments(file, { type: "vider" });
    expect(file.courant).toBeNull();
    expect(file.attente).toEqual([]);
    file = reduireMoments(file, { type: "empiler", moments: ms });
    expect(file.courant).toBeNull();
    expect(file.attente).toEqual([]);
  });

  it("un changement de partie repart d'une file neuve, mémoire comprise", () => {
    const ms = planifierMoments([doubleKo], "a");
    let file = reduireMoments(FILE_MOMENTS_VIDE, { type: "empiler", moments: ms });
    file = reduireMoments(file, { type: "reinitialiser" });
    expect(file).toEqual(FILE_MOMENTS_VIDE);
    // Les numéros de coup d'une autre partie n'ont rien à voir : les mêmes clés doivent rejouer.
    file = reduireMoments(file, { type: "empiler", moments: ms });
    expect(file.courant?.cle).toBe("12:0:ko");
  });

  it("avancer sur une file au repos ne fait rien", () => {
    expect(reduireMoments(FILE_MOMENTS_VIDE, { type: "avancer" })).toEqual(FILE_MOMENTS_VIDE);
  });

  it("fige le retard à la prise, pour que le tempo d'un moment ne change plus en cours de route", () => {
    // Si la compression se lisait sur l'attente COURANTE, l'arrivée d'un coup pendant qu'un K.O.
    // se joue en recalculerait la durée — et l'écran redémarrerait l'animation en plein milieu.
    const ms = planifierMoments([doubleKo], "a");
    let file = reduireMoments(FILE_MOMENTS_VIDE, { type: "empiler", moments: ms });
    expect(file.retard).toBe(3);
    // Un coup de plus arrive : le retard du moment EN COURS ne bouge pas.
    file = reduireMoments(file, {
      type: "empiler",
      moments: planifierMoments([coup(13, [evt("evolution", { joueur: "a" })])], "a"),
    });
    expect(file.retard).toBe(3);
    expect(file.courant?.cle).toBe("12:0:ko");
    // Et le suivant tiré voit, lui, le retard réel à sa prise.
    file = reduireMoments(file, { type: "avancer" });
    expect(file.retard).toBe(3);
    expect(file.courant?.cle).toBe("12:0:recompense");
  });
});

describe("critère n°2 — la prise de deux récompenses se voit comme deux cartes", () => {
  it("deux récompenses donnent deux objets, décalés dans le temps", () => {
    const m = moment("recompense", { objets: 2 });
    const effet = effetMoment(m);
    expect(effet.objets).toHaveLength(2);
    // Des retards égaux auraient donné UN vol groupé : deux cartes qui partent ensemble ne se
    // comptent pas à l'œil. C'est exactement ce que le critère interdit.
    const retards = effet.objets.map((o) => o.retard);
    expect(new Set(retards).size).toBe(2);
    expect(retards[0]).toBe(0);
    expect(retards[1]).toBeGreaterThan(0);
  });

  it("une seule récompense ne donne qu'une carte, sans retard", () => {
    const effet = effetMoment(moment("recompense", { objets: 1 }));
    expect(effet.objets).toHaveLength(1);
    expect(effet.objets[0]?.retard).toBe(0);
  });

  it("jusqu'à six récompenses restent six cartes distinctes (R-14.1 : six au total)", () => {
    const effet = effetMoment(moment("recompense", { objets: 6 }));
    expect(effet.objets).toHaveLength(6);
    expect(new Set(effet.objets.map((o) => o.retard)).size).toBe(6);
  });

  it("le dernier objet parti a encore son premier temps entier à l'écran", () => {
    // Sinon, la seconde récompense d'un moment comprimé serait coupée net — vue, mais pas lue.
    const effet = effetMoment(moment("recompense", { objets: 2 }), { enAttente: 8 });
    const premier = effet.phases[0];
    const dernier = effet.objets[effet.objets.length - 1];
    expect(premier).toBeDefined();
    expect(dernier).toBeDefined();
    expect((dernier?.retard ?? 0) + (premier?.duree ?? 0)).toBeLessThanOrEqual(effet.duree);
  });

  it("la phrase dit le compte, au singulier comme au pluriel", () => {
    expect(phraseMoment(moment("recompense", { objets: 2 }))).toContain("2 cartes");
    expect(phraseMoment(moment("recompense", { objets: 1 }))).toContain("1 carte");
    expect(badgeMoment(moment("recompense", { objets: 2 }))).toBe("+2 récompenses");
    expect(badgeMoment(moment("recompense", { objets: 1 }))).toBe("+1 récompense");
  });

  it("un genre non échelonné ne multiplie pas ses objets", () => {
    // Un K.O. ne fait tomber qu'une carte, même si on lui passait un compte fantaisiste.
    expect(effetMoment(moment("ko", { objets: 5 })).objets).toHaveLength(1);
  });
});

describe("critère n°3 — le pile ou face ne donne jamais une impression de résultat prédéterminé", () => {
  /** Le même lancer de deux pièces, dans ses trois résultats possibles. */
  const lancers = [0, 1, 2].map((faces) =>
    effetMoment(moment("piece", { objets: 2, piece: { pieces: 2, faces } })),
  );

  /** Tout l'effet SAUF ce qui dit le résultat : c'est ce qui doit être rigoureusement identique. */
  function rotationSeule(e: EffetMoment) {
    return {
      phases: e.phases,
      duree: e.duree,
      revelationA: e.revelationA,
      secousse: e.secousse,
      nombre: e.objets.length,
      retards: e.objets.map((o) => o.retard),
      index: e.objets.map((o) => o.index),
    };
  }

  it("la rotation est rigoureusement identique quel que soit le résultat", () => {
    // C'est le cœur du critère : si la durée, le nombre de tours ou les retards dépendaient du
    // résultat, un joueur attentif lirait le tirage avant la fin de l'animation. Ici la rotation
    // est calculée sans jamais lire `faces`.
    const [zero, une, deux] = lancers.map(rotationSeule);
    expect(une).toEqual(zero);
    expect(deux).toEqual(zero);
  });

  it("le résultat n'existe que dans la pose finale de chaque pièce", () => {
    expect(lancers[0]?.objets.map((o) => o.face)).toEqual([false, false]);
    expect(lancers[1]?.objets.map((o) => o.face)).toEqual([true, false]);
    expect(lancers[2]?.objets.map((o) => o.face)).toEqual([true, true]);
  });

  it("la révélation arrive strictement après le début, à la fin du temps de rotation", () => {
    for (const e of lancers) {
      expect(e.revelationA).toBeGreaterThan(0);
      const rotation = e.phases.find((p) => p.nom === "rotation");
      expect(rotation).toBeDefined();
      expect(e.revelationA).toBe((rotation?.debut ?? 0) + (rotation?.duree ?? 0));
      // Et il reste du temps après la révélation : une pose finale invisible ne serait pas une
      // révélation, ce serait une fin de film.
      expect(e.revelationA).toBeLessThan(e.duree);
    }
  });

  it("les genres sans pièce n'ont rien à révéler (et ne font pas semblant)", () => {
    for (const genre of GENRES_MOMENT.filter((g) => g !== "piece")) {
      const e = effetMoment(moment(genre));
      expect(e.revelationA, genre).toBe(0);
      expect(e.objets.every((o) => o.face === null), genre).toBe(true);
    }
  });

  it("reste honnête comprimé : la rotation ne dépend toujours pas du résultat", () => {
    // La compression est le chemin par lequel une dépendance au résultat pourrait se glisser sans
    // qu'on y pense (une durée arrondie différemment selon le nombre d'objets révélés, par exemple).
    for (const enAttente of [0, 3, 12]) {
      const a = effetMoment(moment("piece", { objets: 2, piece: { pieces: 2, faces: 0 } }), {
        enAttente,
      });
      const b = effetMoment(moment("piece", { objets: 2, piece: { pieces: 2, faces: 2 } }), {
        enAttente,
      });
      expect(rotationSeule(b), `enAttente=${enAttente}`).toEqual(rotationSeule(a));
    }
  });

  it("ne tire RIEN au hasard : le résultat vient du serveur, et de lui seul", () => {
    // Garde statique sur la source : un `Math.random` ajouté ici fabriquerait un résultat côté
    // client, et l'écran cesserait d'être un écran. Le socle a la même garde sur son CSS — une
    // intention ne se vérifie pas, une source si.
    const source = readFileSync(
      path.resolve(process.cwd(), "src/lib/game/anim-moments.ts"),
      "utf-8",
    );
    // On ignore les commentaires : ils NOMMENT l'interdit, ils ne le commettent pas.
    const code = source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .split("\n")
      .filter((l) => !l.trimStart().startsWith("//"))
      .join("\n");
    expect(code).not.toContain("Math.random");
    expect(code).not.toContain("Date.now");
    expect(code).not.toContain("crypto");
  });

  it("le module reste pur : ni React, ni DOM, ni réseau", () => {
    const source = readFileSync(
      path.resolve(process.cwd(), "src/lib/game/anim-moments.ts"),
      "utf-8",
    );
    const imports = Array.from(source.matchAll(/^import .*?from "(.*?)";/gm)).map((m) => m[1]);
    for (const i of imports) {
      expect(i, `import interdit : ${i}`).toMatch(/^@\/lib\//);
    }
    for (const interdit of ["document.", "window.", "fetch(", "localStorage"]) {
      expect(source, interdit).not.toContain(interdit);
    }
  });
});

describe("anim-moments — la version réduite dit ce que l'animation aurait montré", () => {
  it.each(GENRES_MOMENT)("%s a une version réduite complète, immobile et lisible", (genre) => {
    const effet = effetMoment(moment(genre), { reduit: true });
    expect(effet.anime).toBe(false);
    // Aucune couche, aucun objet : « animations réduites » veut dire que rien ne bouge, pas que
    // ça bouge moins.
    expect(effet.phases).toEqual([]);
    expect(effet.objets).toEqual([]);
    expect(effet.secousse).toBe(false);
    // Mais l'information reste entière, et elle reste assez longtemps pour être lue.
    expect(effet.duree).toBe(DUREE_REDUITE_MOMENT);
    expect(effet.phrase.length).toBeGreaterThan(20);
    expect(effet.badge.length).toBeGreaterThan(0);
    expect(effet.libelle).toBe(MOMENTS[genre].libelle);
  });

  it("la version réduite du pile ou face donne le résultat, tout de suite", () => {
    // Couper les animations ne doit pas vouloir dire « tu ne sauras pas ce qui est tombé ». Il n'y
    // a plus rien à différer : il n'y a plus de rotation.
    const effet = effetMoment(moment("piece", { objets: 2, piece: { pieces: 2, faces: 1 } }), {
      reduit: true,
    });
    expect(effet.phrase).toContain("1 face sur 2");
    expect(effet.badge).toBe("1/2 face");
    expect(effet.revelationA).toBe(0);
  });

  it("la version réduite du K.O. et de l'évolution nomme le fait et le camp", () => {
    expect(effetMoment(moment("ko", { camp: "adversaire" }), { reduit: true }).phrase).toContain(
      "l'adversaire",
    );
    expect(
      effetMoment(moment("evolution", { detail: "Herbizarre" }), { reduit: true }).phrase,
    ).toContain("Herbizarre");
  });
});

describe("anim-moments — le découpage en temps", () => {
  it.each(GENRES_MOMENT)("%s : la somme des temps vaut EXACTEMENT la durée totale", (genre) => {
    for (const enAttente of [0, 1, 5, 20]) {
      const e = effetMoment(moment(genre), { enAttente });
      expect(e.phases.reduce((s, p) => s + p.duree, 0), `${genre} enAttente=${enAttente}`).toBe(
        e.duree,
      );
      // Et les temps s'enchaînent sans trou ni recouvrement.
      let attendu = 0;
      for (const p of e.phases) {
        expect(p.debut).toBe(attendu);
        attendu += p.duree;
      }
    }
  });

  it("la compression est bornée des deux côtés", () => {
    expect(facteurCompression(0)).toBe(1);
    expect(facteurCompression(2)).toBe(1);
    expect(facteurCompression(4)).toBeLessThan(1);
    expect(facteurCompression(1000)).toBe(COMPRESSION_MIN);
    expect(facteurCompression(Number.NaN)).toBe(1);
  });

  it("une durée comprimée reste strictement positive (un moment perdu serait un bug)", () => {
    for (const genre of GENRES_MOMENT) {
      expect(effetMoment(moment(genre), { enAttente: 10_000 }).duree, genre).toBeGreaterThan(0);
    }
  });
});
