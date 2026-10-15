import { describe, expect, it, vi } from "vitest";

import type { VueCarte, VuePartie, VueJoueur, VuePokemon } from "@/lib/game/plateau";
import {
  PARALLELISME,
  pourcentage,
  precharger,
  urlsAPrecharger,
} from "@/lib/game/prechargement";

/**
 * Pré-chargement des images d'une partie (lot `j-assets-pipeline`).
 *
 * Ce que ces tests tiennent : l'**ordre d'utilité** (ce qui est sur la table d'abord), le
 * dédoublonnage, le fait qu'on ne pré-charge **jamais** la variante de zoom (c'est tout l'objet du
 * budget), une progression **honnête** même quand une image manque, et le parallélisme borné.
 */

let compteur = 0;
function carte(url: string | null): VueCarte {
  compteur += 1;
  return {
    instance_id: `i${compteur}`,
    ref: `r${compteur}`,
    ...(url
      ? { rendu: { origine: "photo" as const, url, url_zoom: `${url}&zoom`, url_repli: "/img/x" } }
      : {}),
  };
}

function pokemon(...cartes: VueCarte[]): VuePokemon {
  return {
    cartes,
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "debout",
  };
}

function joueur(id: string, surcharges: Partial<VueJoueur> = {}): VueJoueur {
  return {
    id,
    actif: null,
    banc: [],
    defausse: [],
    zone_perdue: [],
    pioche_nombre: 40,
    recompenses_nombre: 6,
    ...surcharges,
  };
}

function vue(surcharges: Partial<VuePartie> = {}): VuePartie {
  return {
    schema_version: 1,
    pour: "j1",
    joueurs: [joueur("j1"), joueur("j2")],
    tour: {
      joueur_actif: "j1",
      numero: 1,
      phase: "principale",
      energie_posee: false,
      supporter_joue: false,
      retraite_faite: false,
    },
    stade: null,
    stade_proprietaire: null,
    terminee: false,
    vainqueur: null,
    raison_fin: null,
    ...surcharges,
  };
}

describe("urlsAPrecharger", () => {
  it("ne demande rien quand il n'y a pas de vue", () => {
    expect(urlsAPrecharger(null)).toEqual([]);
    expect(urlsAPrecharger(undefined)).toEqual([]);
  });

  it("charge ce qui est sur la table avant ce qui est consultable", () => {
    const actif = carte("/p/actif");
    const banc = carte("/p/banc");
    const main = carte("/p/main");
    const defausse = carte("/p/defausse");
    const urls = urlsAPrecharger(
      vue({
        joueurs: [
          joueur("j1", {
            actif: pokemon(actif),
            banc: [pokemon(banc)],
            main: [main],
            defausse: [defausse],
          }),
          joueur("j2"),
        ],
      }),
    );
    // L'ordre décide de ce que le joueur voit pendant son premier tour : la défausse vient après.
    expect(urls).toEqual(["/p/actif", "/p/banc", "/p/main", "/p/defausse"]);
  });

  it("ne pré-charge JAMAIS la variante de zoom", () => {
    const urls = urlsAPrecharger(
      vue({ joueurs: [joueur("j1", { actif: pokemon(carte("/p/a")) }), joueur("j2")] }),
    );
    expect(urls).toEqual(["/p/a"]);
    expect(urls.some((u) => u.includes("zoom"))).toBe(false);
  });

  it("ne demande pas deux fois la même image", () => {
    const partagee = "/p/meme-carte";
    const urls = urlsAPrecharger(
      vue({
        joueurs: [
          joueur("j1", {
            actif: pokemon(carte(partagee)),
            banc: [pokemon(carte(partagee))],
            main: [carte(partagee)],
          }),
          joueur("j2"),
        ],
      }),
    );
    expect(urls).toEqual([partagee]);
  });

  it("ignore les cartes sans rendu : une carte face cachée ne coûte aucun octet", () => {
    const urls = urlsAPrecharger(
      vue({
        joueurs: [joueur("j1", { actif: pokemon(carte(null), carte("/p/dessus")) }), joueur("j2")],
      }),
    );
    expect(urls).toEqual(["/p/dessus"]);
  });

  it("prend aussi le stade et les options d'une décision en attente", () => {
    const urls = urlsAPrecharger(
      vue({
        stade: carte("/p/stade"),
        demande: {
          id: "d1",
          destinataire: "j1",
          categorie: "carte",
          libelle: "Choisis une carte",
          regle: "R-7.1",
          obligatoire: true,
          minimum: 1,
          maximum: 1,
          source: {},
          delai_ms: null,
          temps_restant_ms: null,
          options_cartes: [
            {
              id: "o1",
              ref: "r",
              nom: "Pikachu",
              rendu: {
                origine: "photo",
                url: "/p/option",
                url_zoom: "/p/option&zoom",
              },
            },
          ],
        },
      }),
    );
    expect(urls).toContain("/p/stade");
    expect(urls).toContain("/p/option");
  });

  it("rend une liste vide plutôt que de casser l'écran si la vue est incohérente", () => {
    // `separerCamps` lève quand le destinataire n'est pas dans la partie : un pré-chargement est un
    // confort, il n'a pas le droit de faire tomber le plateau.
    expect(urlsAPrecharger(vue({ pour: "inconnu" }))).toEqual([]);
  });
});

describe("precharger", () => {
  it("annonce 100 % tout de suite quand il n'y a rien à charger", async () => {
    const avancees: number[] = [];
    const etat = await precharger([], (a) => avancees.push(pourcentage(a)));
    expect(etat.termine).toBe(true);
    expect(avancees).toEqual([100]);
  });

  it("compte les images réellement arrivées, et finit", async () => {
    const charger = vi.fn().mockResolvedValue(true);
    const etats: number[] = [];
    const etat = await precharger(["/a", "/b", "/c"], (a) => etats.push(pourcentage(a)), {
      charger,
    });
    expect(charger).toHaveBeenCalledTimes(3);
    expect(etat).toEqual({ total: 3, chargees: 3, echouees: 0, termine: true });
    // Première annonce à 0 % (sinon la barre apparaîtrait déjà remplie), dernière à 100 %.
    expect(etats[0]).toBe(0);
    expect(etats[etats.length - 1]).toBe(100);
  });

  it("une image manquante n'immobilise pas la barre à 99 %", async () => {
    // Le cas réel : une variante effacée du stockage. L'écran retombe sur `url_repli`, mais le
    // pré-chargement doit CONCLURE — une barre bloquée est pire qu'une absence de barre.
    const charger = vi.fn(async (url: string) => url !== "/b");
    const etat = await precharger(["/a", "/b", "/c"], () => {}, { charger });
    expect(etat).toEqual({ total: 3, chargees: 2, echouees: 1, termine: true });
    expect(pourcentage(etat)).toBe(100);
  });

  it("ne charge pas plus de PARALLELISME images à la fois", async () => {
    let enCours = 0;
    let maximum = 0;
    const charger = async () => {
      enCours += 1;
      maximum = Math.max(maximum, enCours);
      await new Promise((r) => setTimeout(r, 1));
      enCours -= 1;
      return true;
    };
    const urls = Array.from({ length: 20 }, (_, i) => `/i${i}`);
    await precharger(urls, () => {}, { charger });
    expect(maximum).toBeLessThanOrEqual(PARALLELISME);
    expect(maximum).toBeGreaterThan(1);
  });

  it("s'arrête à la demande : un écran démonté ne laisse pas de requêtes en vol", async () => {
    let demande = 0;
    const charger = async () => {
      demande += 1;
      return true;
    };
    let interrompu = false;
    const avancees: number[] = [];
    const urls = Array.from({ length: 50 }, (_, i) => `/i${i}`);
    const promesse = precharger(urls, (a) => avancees.push(a.chargees), {
      charger,
      interrompu: () => interrompu,
    });
    interrompu = true;
    await promesse;
    expect(demande).toBeLessThan(urls.length);
  });
});

describe("pourcentage", () => {
  it("dit 100 % quand il n'y a rien à attendre, jamais 0 %", () => {
    expect(pourcentage({ total: 0, chargees: 0, echouees: 0, termine: true })).toBe(100);
  });

  it("arrondit sans jamais dépasser les bornes", () => {
    expect(pourcentage({ total: 3, chargees: 1, echouees: 0, termine: false })).toBe(33);
    expect(pourcentage({ total: 3, chargees: 2, echouees: 1, termine: true })).toBe(100);
  });
});
