import { describe, expect, it } from "vitest";

import {
  BUDGET_RATTRAPAGE,
  DUREE_MAX,
  EFFETS,
  FACTEUR_ACCELERE,
  FILE_VIDE,
  type Animation,
  type CoupAnimation,
  type FileAnimations,
  borner,
  dureeEffective,
  planifier,
  planifierCoup,
  rattraper,
  reduireFile,
  restant,
} from "./animations";
import { TYPES_EVENEMENT_CONNUS } from "./journal";

/**
 * Socle d'animation (lot `j-anim-socle`) — la file, ses durées, son rattrapage. **Pur** : aucun
 * navigateur, aucune E/S. La CI fait foi.
 *
 * Ces tests portent les trois critères d'acceptation du lot, et le risque qu'il nomme :
 *
 * 1. aucune animation ne peut empêcher une action légale d'être jouée — ici côté file (elle se
 *    saute, elle se vide), et côté écran dans `components/game/game-board-animations.test.tsx` ;
 * 2. un événement sans animation définie ne bloque ni ne disparaît ;
 * 3. le plancher d'images par seconde est tenu — ici par ses deux conditions mesurables (une
 *    seule animation à la fois, un coût de file négligeable), et mesuré au navigateur dans
 *    `e2e/anim-fluidite.spec.ts`.
 */

/** La durée nominale de l'effet « dégâts », lue dans le registre (et non recopiée ici). */
const DUREE_DEGATS = EFFETS.degats?.duree ?? 0;

/** Le premier élément d'une liste, ou un échec bruyant : un plan vide serait un bug, pas un cas. */
function premier<T>(xs: readonly T[]): T {
  const x = xs[0];
  if (x === undefined) throw new Error("liste vide : le plan d'animations devrait porter une entrée");
  return x;
}

function coup(numero: number, evenements: { type: string; donnees?: Record<string, unknown> }[]): CoupAnimation {
  return { numero, evenements };
}

/** Avance la file jusqu'au repos, par pas de 16 ms (un cadre d'écran à 60 images/s). */
function vidanger(file: FileAnimations, pasMax = 10_000): FileAnimations {
  let f = file;
  let pas = 0;
  while (f.courante && pas < pasMax) {
    f = reduireFile(f, { type: "avancer", dt: 16 });
    pas += 1;
  }
  return f;
}

describe("planifier — une entrée par événement, sans exception", () => {
  it("traduit un événement connu en animation bornée, ciblée sur la carte de base", () => {
    const a = premier(planifierCoup(coup(7, [{ type: "degats", donnees: { cible: "i-pika", valeur: 60 } }]), "a"));
    expect(a.cle).toBe("7:0");
    expect(a.effet).toBe("impact");
    expect(a.duree).toBe(DUREE_DEGATS);
    expect(a.cible).toBe("i-pika");
    expect(a.resume).toBe(false);
  });

  it("place chaque animation dans son camp, lu sur `donnees.joueur` (jamais une déduction)", () => {
    const plan = planifierCoup(
      coup(1, [
        { type: "cartes_piochees", donnees: { joueur: "a", nombre: 2 } },
        { type: "cartes_piochees", donnees: { joueur: "b", nombre: 2 } },
        { type: "etat_checkup", donnees: { etat: "empoisonne" } },
      ]),
      "a",
    );
    expect(plan.map((p) => p.camp)).toEqual(["moi", "adversaire", "auto"]);
  });

  it("range les coups par numéro croissant, quel que soit l'ordre d'arrivée", () => {
    const plan = planifier(
      [coup(3, [{ type: "ko" }]), coup(1, [{ type: "degats" }]), coup(2, [{ type: "fin_tour" }])],
      "a",
    );
    expect(plan.map((p) => p.numero)).toEqual([1, 2, 3]);
  });

  it("borne toute durée du registre à DUREE_MAX — aucune animation ne fait attendre le jeu", () => {
    for (const [type, def] of Object.entries(EFFETS)) {
      expect(def.duree, `durée de ${type}`).toBeGreaterThan(0);
      expect(def.duree, `durée de ${type}`).toBeLessThanOrEqual(DUREE_MAX);
    }
    expect(borner(5_000)).toBe(DUREE_MAX);
    expect(borner(-1)).toBe(0);
    expect(borner(Number.NaN)).toBe(0);
  });
});

describe("critère 2 — un événement sans animation définie ne bloque ni ne disparaît", () => {
  it("produit tout de même son entrée, sans effet et sans durée", () => {
    const a = premier(planifierCoup(coup(4, [{ type: "un_type_que_le_front_ne_connait_pas" }]), "a"));
    expect(a).toBeDefined();
    expect(a.effet).toBeNull();
    expect(a.duree).toBe(0);
    expect(a.type).toBe("un_type_que_le_front_ne_connait_pas");
  });

  it("ne retient JAMAIS la file : la rafale sans effet se vide en un seul pas de temps", () => {
    const sansEffet = Array.from({ length: 30 }, (_, i) => ({ type: `inconnu_${i}` }));
    const plan = planifierCoup(coup(9, [...sansEffet, { type: "ko", donnees: { cible: "i-x" } }]), "a");
    const file = reduireFile(FILE_VIDE, { type: "empiler", animations: plan });
    // Un seul `avancer`, de durée nulle : les 30 entrées muettes sont traversées d'un coup et le
    // K.O. — le seul qui s'anime — devient l'animation courante.
    const apres = reduireFile(file, { type: "avancer", dt: 0 });
    expect(apres.courante?.type).toBe("ko");
    expect(apres.attente).toHaveLength(0);
  });

  it("aucun des 42 types que le serveur diffuse ne se perd en chemin", () => {
    const plan = planifierCoup(
      coup(1, TYPES_EVENEMENT_CONNUS.map((type) => ({ type }))),
      "a",
    );
    expect(plan).toHaveLength(TYPES_EVENEMENT_CONNUS.length);
    expect(plan.map((p) => p.type)).toEqual([...TYPES_EVENEMENT_CONNUS]);
    // Et la file les consomme tous, sans en abandonner un seul.
    const file = vidanger(reduireFile(FILE_VIDE, { type: "empiler", animations: plan }));
    expect(file.courante).toBeNull();
    expect(file.attente).toHaveLength(0);
  });
});

describe("critère 1 — l'animation se saute, et se jette", () => {
  it("`sauter` passe immédiatement à la suivante", () => {
    const plan = planifierCoup(coup(1, [{ type: "ko" }, { type: "degats" }]), "a");
    let file = reduireFile(FILE_VIDE, { type: "empiler", animations: plan });
    expect(file.courante?.type).toBe("ko");
    file = reduireFile(file, { type: "sauter" });
    expect(file.courante?.type).toBe("degats");
    expect(restant(file)).toBe(DUREE_DEGATS);
  });

  it("`vider` ne laisse rien en vol — et ce qui est jeté ne se rejoue pas à la resync suivante", () => {
    const plan = planifierCoup(coup(1, [{ type: "ko" }, { type: "degats" }, { type: "evolution" }]), "a");
    let file = reduireFile(FILE_VIDE, { type: "empiler", animations: plan });
    file = reduireFile(file, { type: "vider" });
    expect(file.courante).toBeNull();
    expect(file.attente).toHaveLength(0);
    // La resync recouvre les mêmes coups : rien ne redémarre (le serveur reste la seule autorité
    // sur l'état, la file n'a pas à rejouer un film déjà abandonné).
    file = reduireFile(file, { type: "empiler", animations: plan });
    expect(file.courante).toBeNull();
  });

  it("une resync qui recouvre un coup déjà animé ne le rejoue pas", () => {
    const plan = planifierCoup(coup(2, [{ type: "degats" }]), "a");
    let file = reduireFile(FILE_VIDE, { type: "empiler", animations: plan });
    file = reduireFile(file, { type: "empiler", animations: plan });
    expect(file.courante?.cle).toBe("2:0");
    expect(file.attente).toHaveLength(0);
  });
});

describe("modes — accéléré et réduit", () => {
  const a: Animation = {
    cle: "1:0",
    numero: 1,
    rang: 0,
    type: "ko",
    effet: "ko",
    duree: 600,
    cible: null,
    camp: "auto",
    resume: false,
    nombre: 1,
  };

  it("accéléré divise la durée, réduit la supprime", () => {
    expect(dureeEffective(a, "normal")).toBe(600);
    expect(dureeEffective(a, "accelere")).toBe(600 / FACTEUR_ACCELERE);
    expect(dureeEffective(a, "reduit")).toBe(0);
  });

  it("en mode réduit, toute la file se vide en un pas de temps nul (prefers-reduced-motion)", () => {
    const plan = planifier(
      [coup(1, [{ type: "ko" }, { type: "degats" }]), coup(2, [{ type: "evolution" }])],
      "a",
    );
    let file = reduireFile({ ...FILE_VIDE, mode: "reduit" }, { type: "empiler", animations: plan });
    file = reduireFile(file, { type: "avancer", dt: 0 });
    expect(file.courante).toBeNull();
    expect(file.attente).toHaveLength(0);
  });
});

describe("critère du lot — rattrapage : vingt événements manqués se résument", () => {
  const vingt = planifier(
    Array.from({ length: 20 }, (_, i) => coup(i + 1, [{ type: "degats", donnees: { cible: `i-${i}` } }])),
    "a",
  );

  it("ne rejoue pas les vingt un par un : un résumé, puis les deux derniers", () => {
    const file = reduireFile(FILE_VIDE, { type: "empiler", animations: vingt });
    const tout = [file.courante, ...file.attente].filter((x): x is Animation => !!x);
    expect(tout).toHaveLength(3);
    expect(premier(tout).resume).toBe(true);
    expect(premier(tout).nombre).toBe(18);
    expect(tout.slice(1).map((t) => t.cle)).toEqual(["19:0", "20:0"]);
  });

  it("la rafale rattrapée tient dans le budget de temps annoncé", () => {
    const apres = rattraper(vingt);
    const total = apres.reduce((s, a) => s + a.duree, 0);
    expect(total).toBeLessThanOrEqual(BUDGET_RATTRAPAGE);
    // Sans rattrapage, les vingt dégâts dureraient bien plus que le budget : c'est ce qu'on évite.
    expect(vingt.reduce((s, a) => s + a.duree, 0)).toBeGreaterThan(BUDGET_RATTRAPAGE);
  });

  it("une rafale courte passe intacte — on ne résume que ce qui déborde", () => {
    const trois = planifier(
      [coup(1, [{ type: "degats" }]), coup(2, [{ type: "ko" }]), coup(3, [{ type: "pokemon_pose" }])],
      "a",
    );
    expect(rattraper(trois)).toEqual(trois);
  });

  it("un rattrapage ne jette aucun événement muet : ils restent dans la file", () => {
    const melange = planifier(
      Array.from({ length: 20 }, (_, i) =>
        coup(i + 1, [{ type: "degats" }, { type: "verrou_pose" }]),
      ),
      "a",
    );
    const apres = rattraper(melange);
    const muets = apres.filter((a) => a.effet === null);
    expect(muets).toHaveLength(20);
  });
});

describe("plancher d'images par seconde — ses deux conditions, mesurées", () => {
  it("UNE animation au plus est jouée à la fois, quelle que soit la rafale", () => {
    const enorme = planifier(
      Array.from({ length: 500 }, (_, i) => coup(i + 1, [{ type: "degats" }, { type: "ko" }])),
      "a",
    );
    let file = reduireFile(FILE_VIDE, { type: "empiler", animations: enorme });
    for (let i = 0; i < 2_000 && file.courante; i += 1) {
      // `courante` est un objet ou `null` : il n'existe pas d'état où deux animations se jouent.
      expect(file.courante).not.toBeNull();
      file = reduireFile(file, { type: "avancer", dt: 16 });
    }
    expect(file.courante).toBeNull();
  });

  it("le coût de la file est négligeable devant un cadre d'écran (16,7 ms)", () => {
    const plan = planifier(
      Array.from({ length: 300 }, (_, i) => coup(i + 1, [{ type: "degats" }])),
      "a",
    );
    // Rattrapage neutralisé à dessein (`seuil`/`budget` hors d'atteinte) : on veut mesurer le coût
    // du réducteur sur une file de 300 animations réellement conservées, pas sur son résumé.
    let file = reduireFile(
      { ...FILE_VIDE, mode: "accelere" },
      { type: "empiler", animations: plan, options: { seuil: 10_000, budget: 10_000_000 } },
    );
    const debut = performance.now();
    let pas = 0;
    while (file.courante && pas < 5_000) {
      file = reduireFile(file, { type: "avancer", dt: 16 });
      pas += 1;
    }
    const total = performance.now() - debut;
    expect(pas).toBeGreaterThan(10);
    // Le réducteur coûte, par pas, une fraction de millisecondes : il ne peut pas être la cause
    // d'une image perdue. Seuil large à dessein — il attrape une régression d'un ordre de
    // grandeur (une copie de tableau devenue quadratique), pas le bruit d'une machine chargée.
    expect(total / pas).toBeLessThan(1);
  });
});
