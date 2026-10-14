import { render } from "@testing-library/react";
import axe, { type Result } from "axe-core";
import { describe, expect, it } from "vitest";

import { ActionBar } from "@/components/game/action-bar";
import { GameBoard } from "@/components/game/game-board";
import { JournalPanel } from "@/components/game/journal-panel";
import { ZoneCachee, ZonePublique } from "@/components/game/zone-consultation";
import { REPOS } from "@/lib/game/interactions";
import type { LigneJournal } from "@/lib/game/journal";
import type { VueJoueur, VuePartie, VuePokemon } from "@/lib/game/plateau";

/**
 * **L'audit d'accessibilité des écrans de jeu** (lot `j-accessibilite-jeu`), premier des deux
 * niveaux.
 *
 * Il n'en existait aucun : le socle attendu n'était écrit qu'en prose dans `docs/UI-UX.md`, et le
 * mot « audit » du prompt du lot n'avait aucun outil derrière lui. Ce fichier en pose un, et le
 * second niveau est dans `e2e/a11y-jeu.spec.ts`. Les deux sont nécessaires, et c'est leur partage
 * qui compte :
 *
 * - **ici, en jsdom** : la structure. Rôles, étiquettes, imbrications interdites, boutons sans nom
 *   accessible, `aria-*` invalides. Rapide (quelques centaines de millisecondes), tourne dans le
 *   job `web` de la CI, donc à chaque poussée ;
 * - **là, dans le navigateur** : ce qui a besoin d'un rendu réel — le **contraste** (`axe` ne sait
 *   pas le calculer sans peinture : jsdom n'a ni couleur effective ni cascade appliquée) et la
 *   **taille des cibles**.
 *
 * Les couleurs des repères du jeu, elles, sont mesurées à la source par
 * `src/__tests__/contraste-jeu.test.ts` — là où elles sont *définies*, donc pour les onze types,
 * y compris ceux qu'aucun écran de test n'affiche.
 */

function pokemon(ref: string, over: Partial<VuePokemon> = {}): VuePokemon {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
    ...over,
  };
}

function carte(ref: string) {
  return { instance_id: `i-${ref}`, ref };
}

const MOI: VueJoueur = {
  id: "a",
  actif: pokemon("moi-actif", { energies: [carte("en1")], compteurs_degats: 20 }),
  banc: [pokemon("moi-banc1")],
  defausse: [carte("moi-defausse1")],
  zone_perdue: [],
  pioche_nombre: 41,
  recompenses_nombre: 6,
  main: [carte("main1"), carte("main2")],
  recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
};

const ADVERSAIRE: VueJoueur = {
  id: "b",
  actif: pokemon("adv-actif", { etats_speciaux: ["endormi"] }),
  banc: [pokemon("adv-banc1")],
  defausse: [carte("adv-defausse1")],
  zone_perdue: [],
  pioche_nombre: 39,
  recompenses_nombre: 5,
  main_nombre: 3,
};

const VUE: VuePartie = {
  schema_version: 1,
  pour: "a",
  joueurs: [MOI, ADVERSAIRE],
  tour: {
    joueur_actif: "a",
    numero: 4,
    phase: "principale",
    energie_posee: false,
    supporter_joue: false,
    retraite_faite: false,
  },
  stade: carte("stade-foret"),
  stade_proprietaire: "a",
  terminee: false,
  vainqueur: null,
  raison_fin: null,
  actions_legales: [
    { type: "attacher_energie", params: {}, etiquette: "Attacher Énergie Eau", cibles: [], irreversible: false },
    { type: "declarer_attaque", params: {}, etiquette: "Pistolet à O", cibles: [], irreversible: true },
  ],
  actions_refusees: [
    {
      type: "retraite",
      params: {},
      etiquette: "Retraite",
      message: "la retraite a déjà été faite ce tour-ci",
      regle: "R-7.3",
      irreversible: false,
    },
  ],
};

const LIGNES: LigneJournal[] = [
  {
    cle: "1:0",
    numero: 1,
    type: "degats",
    texte: "Ton Carapuce met 30 dégâts à Salamèche.",
    traduit: true,
    categorie: "moi",
    refs: [],
    surligne: null,
    detailDegats: "30 base = 30",
  },
];

/**
 * Lance `axe` sur un conteneur et rend les manquements, règles de **contraste et de cibles
 * exclues** : elles exigent un rendu réel (voir l'en-tête) et seraient ici des faux négatifs
 * silencieux — `axe` les marque « incomplete », pas « violation », et on croirait avoir vérifié.
 */
async function manquements(element: HTMLElement): Promise<Result[]> {
  const resultat = await axe.run(element, {
    rules: {
      "color-contrast": { enabled: false },
      "target-size": { enabled: false },
      // `region` exige que tout contenu soit dans un repère ARIA : c'est une règle de PAGE, et on
      // ne rend ici que des fragments. Elle est vérifiée dans l'audit e2e, sur les vraies pages.
      region: { enabled: false },
    },
  });
  return resultat.violations;
}

/** Le détail lisible d'un manquement, pour que l'échec nomme le coupable et pas seulement le compte. */
function decrire(violations: Result[]): string {
  return violations
    .map((v) => `${v.id} (${v.impact}) : ${v.help} → ${v.nodes.map((n) => n.html).join(" | ")}`)
    .join("\n");
}

describe("audit d'accessibilité des écrans de jeu (structure)", () => {
  it("le plateau jouable passe l'audit", async () => {
    const { container } = render(<GameBoard vue={VUE} onJouer={async () => {}} />);
    const v = await manquements(container);
    expect(v, decrire(v)).toEqual([]);
  });

  it("le plateau en lecture seule passe l'audit (replay, spectateur)", async () => {
    const { container } = render(<GameBoard vue={VUE} />);
    const v = await manquements(container);
    expect(v, decrire(v)).toEqual([]);
  });

  it("la barre d'actions passe l'audit, coups refusés compris", async () => {
    const { container } = render(
      <ActionBar
        legales={VUE.actions_legales ?? []}
        refusees={VUE.actions_refusees ?? []}
        selection={REPOS}
        verrou={false}
        onChoisir={() => {}}
        onConfirmer={() => {}}
        onAnnuler={() => {}}
      />,
    );
    const v = await manquements(container);
    expect(v, decrire(v)).toEqual([]);
  });

  it("le journal passe l'audit", async () => {
    const { container } = render(<JournalPanel lignes={LIGNES} />);
    const v = await manquements(container);
    expect(v, decrire(v)).toEqual([]);
  });

  it("les zones (publique ouverte, cachée) passent l'audit", async () => {
    const { container } = render(
      <>
        <ZonePublique titre="défausse" cartes={[carte("roucool")]} />
        <ZoneCachee titre="pioche" nombre={41} />
      </>,
    );
    const v = await manquements(container);
    expect(v, decrire(v)).toEqual([]);
  });

  it("annonce le dernier coup à un lecteur d'écran, tiroir replié", async () => {
    // Le journal est replié par défaut sur le plateau : sans cette région, la partie avançait en
    // silence total pour qui ne voit pas l'écran.
    const { getByTestId } = render(<JournalPanel lignes={LIGNES} />);
    const annonce = getByTestId("journal-annonce");
    expect(annonce).toHaveAttribute("aria-live", "polite");
    expect(annonce).toHaveTextContent("met 30 dégâts");
  });
});
