/**
 * `ActionBar` — les clés React des coups doivent être uniques (lot `j-e2e-deux-navigateurs`).
 *
 * Non-régression d'un défaut qui **empêchait de jouer**. Deux coups légaux distincts partagent très
 * souvent type *et* étiquette : une Énergie par exemplaire en main donne autant de boutons
 * « Attacher <nom> », un Objet en plusieurs exemplaires autant de « Jouer <nom> ». La clé valait
 * `type:etiquette` : tous ces boutons portaient donc la même, React ne réconciliait plus la liste,
 * et après un coup en vol une partie des boutons gardait l'attribut `disabled` du rendu précédent
 * — définitivement. Mesuré sur une partie réelle : 12 `attacher_energie` et 9 `jouer_objet`
 * identiques, dont 4 restés grisés à côté de 5 jouables.
 *
 * Pourquoi personne ne l'avait vu : React n'avertit des clés dupliquées qu'en **développement**, et
 * l'e2e tourne sur un build de production où l'avertissement est retiré.
 *
 * Le test surveille donc `console.error` (c'est par là que React signale les clés dupliquées) **et**
 * vérifie le symptôme observable : tous les boutons d'un même coup suivent le verrou ensemble.
 */

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ActionBar } from "@/components/game/action-bar";
import { REPOS } from "@/lib/game/interactions";
import type { VueActionLegale } from "@/lib/game/plateau";

/** Six fois le même coup, comme le serveur l'envoie pour six Énergies identiques en main. */
function energiesIdentiques(n: number): VueActionLegale[] {
  return Array.from({ length: n }, () => ({
    type: "attacher_energie",
    params: {},
    etiquette: "Attacher Énergie Métal E2E",
    cibles: [{ genre: "pokemon_en_jeu", reference: "j1:d1", etiquette: "Attaquant E2E" }],
    irreversible: false,
  }));
}

function rendre(verrou: boolean) {
  return render(
    <ActionBar
      legales={energiesIdentiques(6)}
      refusees={[]}
      selection={REPOS}
      verrou={verrou}
      onChoisir={() => {}}
      onConfirmer={() => {}}
      onAnnuler={() => {}}
    />,
  );
}

describe("ActionBar — clés des coups", () => {
  let erreurs: string[];

  beforeEach(() => {
    erreurs = [];
    vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      erreurs.push(args.map(String).join(" "));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("n'émet aucun avertissement de clé dupliquée sur plusieurs coups identiques", () => {
    rendre(false);

    const dupliquees = erreurs.filter((e) => /same key|unique "key"|clé/i.test(e));
    expect(
      dupliquees,
      `React signale des clés dupliquées : ${dupliquees.join(" | ")}`,
    ).toHaveLength(0);
  });

  it("libère TOUS les boutons identiques quand le verrou retombe", () => {
    const { rerender } = rendre(true);
    const verrouilles = screen.getAllByTestId("action-attacher_energie");
    expect(verrouilles).toHaveLength(6);
    expect(verrouilles.every((b) => (b as HTMLButtonElement).disabled)).toBe(true);

    // Le coup est retombé : la barre se rouvre. Avec des clés dupliquées, React laissait une
    // partie des boutons grisés — le joueur ne pouvait plus les jouer.
    rerender(
      <ActionBar
        legales={energiesIdentiques(6)}
        refusees={[]}
        selection={REPOS}
        verrou={false}
        onChoisir={() => {}}
        onConfirmer={() => {}}
        onAnnuler={() => {}}
      />,
    );

    const apres = screen.getAllByTestId("action-attacher_energie") as HTMLButtonElement[];
    const grises = apres.filter((b) => b.disabled);
    expect(
      grises,
      `${grises.length} bouton(s) sur ${apres.length} sont restés grisés après le verrou`,
    ).toHaveLength(0);
  });
});
