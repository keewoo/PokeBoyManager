import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoutonSon, useFileSons } from "@/components/game/son-layer";
import { CLE_SONS, SONS, SONS_DEFAUT, type CoupSons } from "@/lib/game/sons";
import { SonsProvider, useSons } from "@/lib/sons-provider";

/**
 * Le fournisseur de son (lot `j-son`) : **quand** le son s'ouvre, et **ce que couper veut dire**.
 *
 * Les deux tests qui portent des critères d'acceptation du lot :
 *
 * - *« aucun son ne se déclenche avant une interaction du joueur »* — ici en prouvant qu'aucun
 *   `AudioContext` n'est même **construit** avant le premier geste. C'est plus fort que la règle du
 *   navigateur : un contexte créé trop tôt naît suspendu et écrit un avertissement dans la console
 *   de chaque visiteur, puis déverse les sons en retard au premier clic ;
 * - *« la coupure est immédiate et mémorisée »* — immédiate par le volume général mis à zéro dans
 *   le geste même, mémorisée par `localStorage` (DJ9 : **par appareil**, pas par compte).
 *
 * L'`AudioContext` est remplacé par un faux qui **compte** ce qu'on lui demande. C'est ce qui rend
 * ces propriétés vérifiables en CI, sans navigateur ni carte son.
 */

/** Un nœud de gain factice : il retient la dernière valeur posée, pour qu'on puisse l'affirmer. */
function fauxGain() {
  return {
    gain: {
      value: 0,
      setValueAtTime: vi.fn(),
      linearRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(),
  };
}

type Compteurs = {
  /** Nombre de contextes construits. Doit valoir 0 avant tout geste du joueur. */
  contextes: number;
  /** Nombre d'oscillateurs démarrés — donc de sons réellement lancés. */
  oscillateurs: number;
  /** Nombre de sources de bruit démarrées. */
  bruits: number;
  /** Le nœud de volume général du dernier contexte construit. */
  maitre: ReturnType<typeof fauxGain> | null;
};

const compteurs: Compteurs = { contextes: 0, oscillateurs: 0, bruits: 0, maitre: null };

/** Installe un faux `AudioContext` qui compte tout, et ne produit aucun son. */
function installerFauxAudio() {
  compteurs.contextes = 0;
  compteurs.oscillateurs = 0;
  compteurs.bruits = 0;
  compteurs.maitre = null;

  class FauxContexte {
    currentTime = 0;
    sampleRate = 48_000;
    destination = {};
    constructor() {
      compteurs.contextes += 1;
    }
    createGain() {
      const g = fauxGain();
      // Le premier gain créé par un contexte est le volume général (`creerMoteur`).
      if (compteurs.maitre === null) compteurs.maitre = g;
      return g;
    }
    createBiquadFilter() {
      return { type: "", frequency: { value: 0 }, connect: vi.fn() };
    }
    createBuffer(_canaux: number, longueur: number) {
      const donnees = new Float32Array(longueur);
      return { getChannelData: () => donnees };
    }
    createBufferSource() {
      return {
        buffer: null,
        connect: vi.fn(),
        start: () => {
          compteurs.bruits += 1;
        },
        stop: vi.fn(),
      };
    }
    createOscillator() {
      return {
        type: "",
        frequency: { value: 0, setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn() },
        connect: vi.fn(),
        start: () => {
          compteurs.oscillateurs += 1;
        },
        stop: vi.fn(),
      };
    }
  }

  // `createBuffer` du faux rend un objet minimal : le moteur n'en lit que `getChannelData`.
  vi.stubGlobal("AudioContext", FauxContexte as unknown as typeof AudioContext);
}

/** Sonde : affiche les réglages courants et offre de quoi jouer un son à la demande. */
function Sonde() {
  const { reglages, jouer, pret } = useSons();
  return (
    <>
      <output data-testid="reglages">{JSON.stringify(reglages)}</output>
      <output data-testid="pret">{String(pret)}</output>
      <button type="button" data-testid="jouer" onClick={() => jouer(SONS.pose)}>
        jouer
      </button>
    </>
  );
}

/**
 * Le compteur de sons volontairement passés, lu APRÈS le rendu.
 *
 * Il n'est pas affiché dans le DOM, et c'est volontaire : la couche sonore ne provoque **aucun
 * re-rendu** (c'est ce qui l'empêche de coûter des images par seconde — voir `son-layer.tsx`).
 * Un `<output>` afficherait donc la valeur du rendu précédent, et le test mesurerait le retard de
 * React plutôt que le comportement de la file.
 */
let lireIgnores: () => number = () => 0;

/** Monte la file de sons sur des coups donnés, comme le fait l'écran de partie. */
function PlateauSonore({ coups }: { coups: CoupSons[] }) {
  const sons = useFileSons({ coups, pour: "a", cle: "partie" });
  lireIgnores = sons.ignores;
  return null;
}

describe("fournisseur de son — le moment où le son s'ouvre", () => {
  beforeEach(() => {
    window.localStorage.clear();
    installerFauxAudio();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("ne construit AUCUN contexte audio au chargement de la page", () => {
    render(
      <SonsProvider>
        <Sonde />
      </SonsProvider>,
    );
    // Critère d'acceptation n°3, dans sa forme la plus forte : rien n'existe encore.
    expect(compteurs.contextes).toBe(0);
    expect(screen.getByTestId("pret")).toHaveTextContent("false");
  });

  it("ne joue RIEN si on le lui demande avant le premier geste du joueur", () => {
    render(
      <SonsProvider>
        <Sonde />
      </SonsProvider>,
    );
    // Un coup du serveur peut arriver avant que le joueur n'ait touché l'écran (reprise après F5 :
    // la resync livre toute la partie). Il ne doit pas ouvrir le son — un coup n'est pas un geste.
    act(() => {
      screen.getByTestId("jouer").click();
    });
    expect(compteurs.contextes).toBe(0);
    expect(compteurs.oscillateurs).toBe(0);
  });

  it("ouvre le son au premier geste, et une seule fois", () => {
    render(
      <SonsProvider>
        <Sonde />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
    });
    expect(compteurs.contextes).toBe(1);
    expect(screen.getByTestId("pret")).toHaveTextContent("true");
    // Un second geste ne doit pas empiler un second contexte (les navigateurs en limitent le
    // nombre, et deux contextes doubleraient le volume).
    act(() => {
      fireEvent.pointerDown(window);
      fireEvent.keyDown(window, { key: "a" });
    });
    expect(compteurs.contextes).toBe(1);
  });

  it("joue réellement une fois le son ouvert", () => {
    render(
      <SonsProvider>
        <Sonde />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
    });
    act(() => {
      screen.getByTestId("jouer").click();
    });
    // `pose` a deux partiels : un triangle et du bruit.
    expect(compteurs.oscillateurs).toBe(1);
    expect(compteurs.bruits).toBe(1);
  });

  it("n'ouvre pas le son au premier geste quand tout est coupé sur cet appareil", () => {
    window.localStorage.setItem(CLE_SONS, JSON.stringify({ bruitages: false, musique: false, volume: 0.7 }));
    render(
      <SonsProvider>
        <Sonde />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
    });
    // Rien à ouvrir : on ne fabrique pas un contexte audio pour quelqu'un qui a demandé le silence.
    expect(compteurs.contextes).toBe(0);
  });
});

describe("couper le son — immédiat et mémorisé", () => {
  beforeEach(() => {
    window.localStorage.clear();
    installerFauxAudio();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("applique la décision DJ9 par défaut : bruitages activés, musique coupée", () => {
    render(
      <SonsProvider>
        <Sonde />
      </SonsProvider>,
    );
    expect(screen.getByTestId("reglages")).toHaveTextContent(JSON.stringify(SONS_DEFAUT));
  });

  it("coupe IMMÉDIATEMENT : le volume général tombe à zéro dans le geste même", () => {
    render(
      <SonsProvider>
        <BoutonSon />
      </SonsProvider>,
    );
    // Le son est d'abord ouvert (un geste), sinon il n'y a aucun volume à faire tomber — on ne
    // fabrique pas un contexte audio pour le mettre à zéro.
    act(() => {
      fireEvent.pointerDown(window);
    });
    expect(compteurs.maitre?.gain.value).toBeCloseTo(SONS_DEFAUT.volume);

    const bascule = screen.getByTestId("son-bascule");
    expect(bascule).toHaveAttribute("aria-pressed", "true");
    act(() => {
      bascule.click();
    });
    expect(bascule).toHaveAttribute("aria-pressed", "false");
    // Immédiat : le volume est à zéro avant même le prochain rendu de React.
    expect(compteurs.maitre?.gain.value).toBe(0);
  });

  it("ne fabrique PAS de contexte audio juste pour couper, quand rien n'était ouvert", () => {
    render(
      <SonsProvider>
        <BoutonSon />
      </SonsProvider>,
    );
    act(() => {
      screen.getByTestId("son-bascule").click();
    });
    // Le réglage est pris (et mémorisé), mais il n'y avait rien à éteindre.
    expect(screen.getByTestId("son-bascule")).toHaveAttribute("aria-pressed", "false");
    expect(compteurs.contextes).toBe(0);
  });

  it("MÉMORISE la coupure sur cet appareil (DJ9), et la relit au rechargement", () => {
    const { unmount } = render(
      <SonsProvider>
        <BoutonSon />
      </SonsProvider>,
    );
    act(() => {
      screen.getByTestId("son-bascule").click();
    });
    expect(JSON.parse(window.localStorage.getItem(CLE_SONS) ?? "{}").bruitages).toBe(false);
    unmount();

    // Rechargement de la page : le réglage est relu, la bascule est déjà sur « coupé ».
    render(
      <SonsProvider>
        <BoutonSon />
      </SonsProvider>,
    );
    expect(screen.getByTestId("son-bascule")).toHaveAttribute("aria-pressed", "false");
  });

  it("rétablit le son sans rien déverser de ce qui n'a pas été entendu", () => {
    render(
      <SonsProvider>
        <BoutonSon />
        <Sonde />
      </SonsProvider>,
    );
    const bascule = screen.getByTestId("son-bascule");
    act(() => {
      bascule.click(); // coupé
    });
    act(() => {
      bascule.click(); // rétabli
    });
    expect(bascule).toHaveAttribute("aria-pressed", "true");
    expect(compteurs.maitre?.gain.value).toBeCloseTo(SONS_DEFAUT.volume);
    // Rien n'a sonné du seul fait de rétablir : il faut un nouvel événement pour entendre.
    expect(compteurs.oscillateurs).toBe(0);
  });

  it("garde le réglage par appareil hors de la clé du confort du compte", () => {
    render(
      <SonsProvider>
        <BoutonSon />
      </SonsProvider>,
    );
    act(() => {
      screen.getByTestId("son-bascule").click();
    });
    // Le confort (animations, taille du texte, décor) suit le COMPTE et vit sous sa propre clé.
    // Les mélanger ferait voyager un volume d'un appareil à l'autre, contre DJ9.
    expect(window.localStorage.getItem("pbm.jeu.confort")).toBeNull();
    expect(window.localStorage.getItem(CLE_SONS)).not.toBeNull();
  });
});

describe("la file de sons branchée sur les coups", () => {
  beforeEach(() => {
    window.localStorage.clear();
    installerFauxAudio();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("fait sonner un coup qui ARRIVE après le premier geste", () => {
    const { rerender } = render(
      <SonsProvider>
        <PlateauSonore coups={[]} />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
    });
    const coups: CoupSons[] = [{ numero: 1, evenements: [{ type: "pokemon_pose", donnees: { joueur: "a" } }] }];
    act(() => {
      rerender(
        <SonsProvider>
          <PlateauSonore coups={coups} />
        </SonsProvider>,
      );
      vi.advanceTimersByTime(300);
    });
    // `pose` a deux partiels : un triangle et du souffle.
    expect(compteurs.oscillateurs + compteurs.bruits).toBeGreaterThan(0);
  });

  it("ne rejoue PAS l'histoire : les coups déjà diffusés à l'arrivée du joueur sont comptés, pas joués", () => {
    // Le cas réel est un F5 au quatre-vingtième tour : la resynchronisation livre toute la partie
    // d'un bloc. Les tenir en réserve ferait entendre un K.O. d'il y a dix minutes au moment où le
    // joueur touche l'écran pour la première fois.
    const evenements = Array.from({ length: 20 }, () => ({ type: "cartes_piochees", donnees: { joueur: "a" } }));
    render(
      <SonsProvider>
        <PlateauSonore coups={[{ numero: 1, evenements }]} />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
      vi.advanceTimersByTime(2_000);
    });
    expect(compteurs.oscillateurs).toBe(0);
    expect(compteurs.bruits).toBe(0);
    // Rien n'est perdu en silence : le compte le dit, et le journal porte les vingt phrases.
    expect(lireIgnores()).toBe(20);
  });

  it("résume une rafale arrivée APRÈS le premier geste au lieu de jouer vingt sons", () => {
    const { rerender } = render(
      <SonsProvider>
        <PlateauSonore coups={[]} />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
    });
    const evenements = Array.from({ length: 20 }, () => ({ type: "cartes_piochees", donnees: { joueur: "a" } }));
    act(() => {
      rerender(
        <SonsProvider>
          <PlateauSonore coups={[{ numero: 1, evenements }]} />
        </SonsProvider>,
      );
      vi.advanceTimersByTime(2_000);
    });
    // Un seul son joué (`pioche` = du souffle + une note faible), dix-neuf comptés.
    expect(lireIgnores()).toBe(19);
    expect(compteurs.bruits).toBe(1);
  });

  it("ne sonne pas du tout quand les bruitages sont coupés sur cet appareil", () => {
    window.localStorage.setItem(CLE_SONS, JSON.stringify({ bruitages: false, musique: false, volume: 0.7 }));
    const coups: CoupSons[] = [
      { numero: 1, evenements: [{ type: "ko", donnees: { joueur: "b", par: "a", recompenses_prises: 1 } }] },
    ];
    render(
      <SonsProvider>
        <PlateauSonore coups={coups} />
      </SonsProvider>,
    );
    act(() => {
      fireEvent.pointerDown(window);
      vi.advanceTimersByTime(1_000);
    });
    expect(compteurs.oscillateurs).toBe(0);
    expect(compteurs.bruits).toBe(0);
  });
});
