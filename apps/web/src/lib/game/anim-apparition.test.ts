import { describe, expect, it } from "vitest";

import type { CalqueApparition, CalqueCalcule } from "@/lib/game/anim-apparition";
import {
  AMPLITUDE_BASE,
  CALQUES,
  COUT_LE_PLUS_LOURD,
  DUREES,
  MOTIFS,
  PARTICULES_MAX,
  PROFONDEURS,
  TOTAL_MAX_MS,
  apparitionDe,
  coutVisuel,
  phraseApparition,
  signalApparition,
} from "@/lib/game/anim-apparition";
import type { Animation } from "@/lib/game/animations";
import type { SpecType } from "@/lib/game/anim-types";
import {
  SPECS,
  TYPAGE_VIDE,
  TYPE_LE_PLUS_LOURD,
  coutVisuel as coutVisuel_type,
} from "@/lib/game/anim-types";

/** Une animation du socle, réduite à ce dont l'apparition a besoin. */
function animation(partiel: Partial<Animation> = {}): Animation {
  return {
    cle: "7:0",
    numero: 7,
    rang: 0,
    type: "pokemon_pose",
    effet: "pose",
    duree: 300,
    cible: "carte-a",
    camp: "moi",
    resume: false,
    nombre: 1,
    typage: null,
    ...partiel,
  };
}

const URL = "/img/apparitions/base1-4";

describe("signalApparition — les trois moments, et seulement eux", () => {
  it("reconnaît la pose, l'évolution et l'attaque", () => {
    for (const [type, motif] of Object.entries(MOTIFS)) {
      expect(signalApparition(animation({ type }))?.motif).toBe(motif);
    }
  });

  it("ne reconnaît RIEN d'autre — un Pokémon qui jaillit à chaque énergie attachée n'est plus un événement", () => {
    for (const type of ["energie_attachee", "degats", "ko", "retraite_effectuee", "tour_commence"]) {
      expect(signalApparition(animation({ type }))).toBeNull();
    }
  });

  it("ne se déclenche jamais pendant la mise en place (R-2.4) : ce n'est pas un `pokemon_pose`", () => {
    // Les placements du début de partie passent par `mise_en_place_revelee` — six apparitions
    // d'affilée feraient de la première impression une bousculade, et les découpes feraient
    // exploser le budget de mise en place (432 Kio, `docs/jeu/ASSETS.md`).
    expect(signalApparition(animation({ type: "mise_en_place_revelee" }))).toBeNull();
    expect(signalApparition(animation({ type: "main_revelee" }))).toBeNull();
  });

  it("ignore une animation de résumé : « 18 coups rejoués » ne fait surgir personne", () => {
    expect(signalApparition(animation({ resume: true, type: "attaque_declaree" }))).toBeNull();
  });

  it("ignore une animation sans cible — il n'y aurait aucune carte au-dessus de laquelle apparaître", () => {
    expect(signalApparition(animation({ cible: null }))).toBeNull();
  });

  it("tire l'intensité d'une attaque du résultat réel, pas d'une valeur nominale", () => {
    const faible = signalApparition(
      animation({ type: "attaque_declaree", typage: { ...TYPAGE_VIDE, type: "fire", degats: 10 } }),
    );
    const fort = signalApparition(
      animation({ type: "attaque_declaree", typage: { ...TYPAGE_VIDE, type: "fire", degats: 200 } }),
    );
    expect(faible!.intensite).toBeLessThan(fort!.intensite);
    expect(faible!.type).toBe("fire");
  });

  it("borne l'intensité dans [0, 1] quelles que soient les données du serveur", () => {
    const signal = signalApparition(
      animation({ type: "attaque_declaree", typage: { ...TYPAGE_VIDE, type: "fire", degats: 9999 } }),
    );
    expect(signal!.intensite).toBeGreaterThanOrEqual(0);
    expect(signal!.intensite).toBeLessThanOrEqual(1);
  });
});

describe("apparitionDe — la dégradation est le cas courant, pas l'exception", () => {
  const signal = signalApparition(animation())!;

  it("sans découpe publiée, aucune apparition — et donc aucun trou à l'écran", () => {
    expect(apparitionDe(signal, "carte-a", null)).toBeNull();
    expect(apparitionDe(signal, "carte-a", undefined)).toBeNull();
    expect(apparitionDe(signal, "carte-a", "")).toBeNull();
  });

  it("ne se joue pas sur une autre carte que celle visée", () => {
    expect(apparitionDe(signal, "carte-b", URL)).toBeNull();
  });

  it("ne se joue pas quand les animations sont réduites", () => {
    expect(apparitionDe(signal, "carte-a", URL, { reduit: true })).toBeNull();
  });

  it("sans signal, rien", () => {
    expect(apparitionDe(null, "carte-a", URL)).toBeNull();
  });
});

describe("apparitionDe — la parallaxe", () => {
  const signal = signalApparition(animation())!;
  const apparition = apparitionDe(signal, "carte-a", URL)!;

  it("empile les quatre calques, dans l'ordre déclaré", () => {
    expect(apparition.calques.map((c) => c.calque)).toEqual([...CALQUES]);
  });

  it("donne à chaque calque une amplitude PROPORTIONNELLE à sa profondeur — c'est toute la parallaxe", () => {
    const parNom = Object.fromEntries(
      apparition.calques.map((c) => [c.calque, c]),
    ) as Record<CalqueApparition, CalqueCalcule>;
    expect(parNom.sujet.amplitude).toBeGreaterThan(parNom.echo.amplitude);
    expect(parNom.echo.amplitude).toBeGreaterThan(parNom.halo.amplitude);
    // Si toutes les amplitudes étaient égales, les calques bougeraient d'un bloc et il n'y aurait
    // plus aucun relief : c'est la panne que ce test existe pour attraper.
    const distinctes = new Set(apparition.calques.map((c) => c.amplitude));
    expect(distinctes.size).toBeGreaterThan(1);
  });

  it("fait partir les calques du fond EN PREMIER : le retard décroît avec la profondeur", () => {
    const parNom = Object.fromEntries(
      apparition.calques.map((c) => [c.calque, c]),
    ) as Record<CalqueApparition, CalqueCalcule>;
    expect(parNom.halo.retard).toBeGreaterThan(parNom.sujet.retard);
    expect(parNom.sujet.retard).toBe(0);
  });

  it("ne dépasse jamais l'amplitude de base, même à pleine intensité", () => {
    const fort = apparitionDe(
      signalApparition(
        animation({
          type: "attaque_declaree",
          typage: { ...TYPAGE_VIDE, type: "fire", degats: 300, faiblesse: true },
        }),
      )!,
      "carte-a",
      URL,
    )!;
    for (const calque of fort.calques) {
      // +0,05 : les amplitudes sont arrondies au dixième pour rester lisibles dans le CSS, et
      // cet arrondi peut dépasser la borne exacte d'un demi-dixième. L'invariant porte sur
      // l'amplitude, pas sur sa décimale.
      expect(calque.amplitude).toBeLessThanOrEqual(
        AMPLITUDE_BASE * PROFONDEURS[calque.calque] + 0.05,
      );
    }
  });
});

describe("apparitionDe — le coût reste borné", () => {
  it("ne masque jamais le plateau plus d'une seconde, quel que soit le motif", () => {
    for (const motif of Object.values(MOTIFS)) {
      expect(DUREES[motif]).toBeLessThanOrEqual(TOTAL_MAX_MS);
    }
    for (const type of Object.keys(MOTIFS)) {
      const a = apparitionDe(signalApparition(animation({ type }))!, "carte-a", URL)!;
      expect(a.duree).toBeGreaterThan(0);
      expect(a.duree).toBeLessThanOrEqual(TOTAL_MAX_MS);
    }
  });

  it("plafonne les particules — au-delà c'est du bruit, et c'est du travail par image", () => {
    const a = apparitionDe(
      signalApparition(
        animation({
          type: "attaque_declaree",
          typage: { ...TYPAGE_VIDE, type: "lightning", degats: 300, faiblesse: true },
        }),
      )!,
      "carte-a",
      URL,
    )!;
    expect(a.particules.length).toBeLessThanOrEqual(PARTICULES_MAX);
  });

  it("une pose n'a aucune particule : il n'y a pas de type d'attaque à raconter", () => {
    const a = apparitionDe(signalApparition(animation())!, "carte-a", URL)!;
    expect(a.particules).toHaveLength(0);
  });

  it("fait monter les particules, jamais tomber sous la carte où elles seraient cachées", () => {
    const a = apparitionDe(
      signalApparition(
        animation({
          type: "attaque_declaree",
          typage: { ...TYPAGE_VIDE, type: "lightning", degats: 150 },
        }),
      )!,
      "carte-a",
      URL,
    )!;
    expect(a.particules.length).toBeGreaterThan(0);
    for (const p of a.particules) {
      expect(p.angle).toBeGreaterThanOrEqual(-150);
      expect(p.angle).toBeLessThanOrEqual(-30);
    }
  });
});

describe("apparitionDe — ce qu'elle porte", () => {
  it("change de clé à chaque coup : sans ça, deux attaques d'affilée ne rejoueraient rien", () => {
    const a = apparitionDe(signalApparition(animation({ cle: "7:0" }))!, "carte-a", URL)!;
    const b = apparitionDe(signalApparition(animation({ cle: "8:0" }))!, "carte-a", URL)!;
    expect(a.cle).not.toBe(b.cle);
  });

  it("donne une phrase à chaque motif — l'effet n'est jamais muet pour la galerie", () => {
    for (const motif of Object.values(MOTIFS)) {
      expect(phraseApparition(motif).length).toBeGreaterThan(10);
    }
  });
});

describe("le coût d'affichage reste sous le plafond de fluidité", () => {
  it("ne met jamais en mouvement plus de nœuds que l'effet typé le plus lourd", () => {
    // Le plancher de 30 images/s est déjà tenu, mesuré, avec les effets typés les plus chargés
    // (`e2e/anim-fluidite.spec.ts`, sur `TYPE_LE_PLUS_LOURD`). Si l'apparition n'ajoute pas plus de
    // nœuds animés que ce qui est déjà admis, elle ne peut pas être ce qui fait tomber le plancher.
    // C'est une borne vérifiable en CI, là où une mesure de temps serait bruitée.
    const coutTypeLePlusLourd = coutVisuel_type(SPECS[TYPE_LE_PLUS_LOURD] as SpecType);
    expect(COUT_LE_PLUS_LOURD).toBeLessThanOrEqual(coutTypeLePlusLourd);
  });

  it("borne le coût de TOUTE apparition réellement composable", () => {
    for (const type of Object.keys(MOTIFS)) {
      for (const degats of [0, 30, 90, 200, 400]) {
        const a = apparitionDe(
          signalApparition(
            animation({ type, typage: { ...TYPAGE_VIDE, type: "lightning", degats } }),
          )!,
          "carte-a",
          URL,
        );
        if (a) expect(coutVisuel(a)).toBeLessThanOrEqual(COUT_LE_PLUS_LOURD);
      }
    }
  });

  it("une seule apparition peut se jouer à la fois — le budget serveur n'en compte qu'une", () => {
    // `budget.postes_partie()` compte 1 × 40 Kio d'apparition par partie. Deux apparitions
    // simultanées le mettraient en défaut, et le plateau dépasserait les 2304 Kio garantis.
    // L'invariant est tenu par le socle : la file n'expose qu'une `Animation` courante, donc
    // `signalApparition` ne peut produire qu'un signal, donc une seule carte s'allume.
    const signal = signalApparition(animation())!;
    const sur = ["carte-a", "carte-b", "carte-c"]
      .map((ref) => apparitionDe(signal, ref, URL))
      .filter(Boolean);
    expect(sur).toHaveLength(1);
  });
});
