import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoucheAnimation, useFileMoments } from "./animation-layer";
import { EffetMomentCle } from "./effet-moment";
import { type CoupAnimation } from "@/lib/game/animations";
import {
  type GenreMoment,
  GENRES_MOMENT,
  MOMENTS,
  type MomentPlanifie,
  effetMoment,
} from "@/lib/game/anim-moments";

/**
 * Le rendu et le branchement des **moments clés** (lot `j-anim-evolution-ko`).
 *
 * Ce que ces tests prouvent, et qu'aucun test pur ne peut prouver :
 *
 * - un **double K.O.** fait défiler ses quatre moments à l'écran, l'un après l'autre, et le dernier
 *   ne manque pas (critère n°1 — la version pure en prouve l'ordre, celle-ci qu'ils sont bien
 *   *rendus*) ;
 * - **deux récompenses** donnent deux objets dans le DOM (critère n°2) ;
 * - un moment **remplace** la pastille du socle, il ne s'y ajoute pas : aucune occlusion de plus ;
 * - il ne capture **jamais** un clic, et il se **coupe** même quand il se joue seul ;
 * - en animations réduites, la phrase est **annoncée** — elle devient le seul canal.
 */

/** Pose la réponse de `matchMedia` pour `prefers-reduced-motion`. */
function poserReducedMotion(matches: boolean) {
  const faux = (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? matches : false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
  window.matchMedia = faux as unknown as typeof window.matchMedia;
}

/** Un moment planifié du genre demandé. */
function moment(genre: GenreMoment, patch: Partial<MomentPlanifie> = {}): MomentPlanifie {
  return {
    cle: `1:0:${genre}`,
    genre,
    numero: 1,
    rang: 0,
    cible: null,
    camp: "moi",
    objets: 2,
    piece: genre === "piece" ? { pieces: 2, faces: 1 } : null,
    detail: null,
    ...patch,
  };
}

/** Le coup d'un double K.O. (R-13.5), chacun avec sa récompense : quatre moments. */
const DOUBLE_KO: CoupAnimation[] = [
  {
    numero: 1,
    evenements: [
      { type: "ko", donnees: { joueur: "a", pokemon: "i-1", recompenses_prises: 1, par: "b" } },
      { type: "ko", donnees: { joueur: "b", pokemon: "i-2", recompenses_prises: 1, par: "a" } },
    ],
  },
];

/** Monte le crochet dans un composant témoin qui expose son état. */
function Temoin({ liste, pour = "a" }: { liste: CoupAnimation[]; pour?: string }) {
  const m = useFileMoments({ coups: liste, pour, cle: "g1" });
  return (
    <div>
      <span data-testid="genre">{m.moment?.genre ?? "aucun"}</span>
      <span data-testid="cle">{m.moment?.cle ?? "-"}</span>
      <span data-testid="attente">{m.enAttente}</span>
      <button type="button" data-testid="passer" onClick={m.sauter}>
        passer
      </button>
      <button type="button" data-testid="vider" onClick={m.vider}>
        vider
      </button>
    </div>
  );
}

beforeEach(() => {
  poserReducedMotion(false);
  vi.useFakeTimers({ shouldAdvanceTime: false });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("EffetMomentCle — le rendu d'un moment", () => {
  it("ne rend rien sans moment", () => {
    const { container } = render(<EffetMomentCle effet={null} />);
    expect(container.firstChild).toBeNull();
  });

  it.each(GENRES_MOMENT)("%s se dessine avec ses couches et son libellé", (genre) => {
    render(<EffetMomentCle effet={effetMoment(moment(genre))} />);
    const scene = screen.getByTestId("fx-moment");
    expect(scene.getAttribute("data-genre")).toBe(genre);
    // Autant de couches que la table en déclare, tous temps confondus.
    const attendues = MOMENTS[genre].phases.reduce((s, p) => s + p.couches.length, 0);
    expect(scene.querySelectorAll(".pbm-m-couche")).toHaveLength(attendues);
    expect(screen.getByTestId("fx-moment-libelle").textContent).toBe(MOMENTS[genre].libelle);
  });

  it("ne capture jamais un clic (une animation n'empêche pas de jouer)", () => {
    render(<EffetMomentCle effet={effetMoment(moment("ko"))} />);
    expect(screen.getByTestId("fx-moment").className).toContain("pointer-events-none");
  });

  it("chaque temps porte son départ et sa durée, calculés par le module", () => {
    const effet = effetMoment(moment("ko"));
    render(<EffetMomentCle effet={effet} />);
    const couches = Array.from(
      screen.getByTestId("fx-moment").querySelectorAll<HTMLElement>(".pbm-m-couche"),
    );
    // Le CSS ne décide d'aucune durée : il les lit. C'est ce qui permet de comprimer une rafale
    // sans toucher à la feuille de style.
    for (const c of couches) {
      expect(c.style.getPropertyValue("--pbm-m-duree")).toMatch(/^\d+ms$/);
      expect(c.style.getPropertyValue("--pbm-m-debut")).toMatch(/^\d+ms$/);
    }
    const phase = effet.phases.find((p) => p.couches.includes("voile"));
    const voile = screen.getByTestId("fx-moment").querySelector<HTMLElement>('[data-couche="voile"]');
    expect(voile?.style.getPropertyValue("--pbm-m-debut")).toBe(`${phase?.debut}ms`);
  });

  it("enchaîne les gestes de l'objet dans l'ordre des temps", () => {
    // Le premier geste est en `both`, les suivants en `forwards` : sans ça, un geste en attente
    // appliquerait sa pose de départ par-dessus le geste en cours, et la carte sauterait.
    render(<EffetMomentCle effet={effetMoment(moment("ko"))} />);
    const objet = screen
      .getByTestId("fx-moment")
      .querySelector<HTMLElement>(".pbm-m-objet") as HTMLElement;
    const animation = objet.style.animation;
    expect(animation).toContain("pbm-anim-fx-m-bascule");
    expect(animation).toContain("pbm-anim-fx-m-envol");
    expect(animation.indexOf("bascule")).toBeLessThan(animation.indexOf("envol"));
    expect(animation).toContain("both");
    expect(animation).toContain("forwards");
  });
});

describe("critère n°2 (à l'écran) — deux récompenses sont deux cartes dans le DOM", () => {
  it("rend deux objets, décalés", () => {
    render(<EffetMomentCle effet={effetMoment(moment("recompense", { objets: 2 }))} />);
    const objets = Array.from(
      screen.getByTestId("fx-moment").querySelectorAll<HTMLElement>(".pbm-m-objet"),
    );
    expect(objets).toHaveLength(2);
    expect(objets.map((o) => o.getAttribute("data-objet"))).toEqual(["carte", "carte"]);
    const retards = objets.map((o) => o.style.getPropertyValue("--pbm-m-retard"));
    expect(new Set(retards).size).toBe(2);
  });

  it("une seule récompense ne rend qu'une carte", () => {
    render(<EffetMomentCle effet={effetMoment(moment("recompense", { objets: 1 }))} />);
    expect(
      screen.getByTestId("fx-moment").querySelectorAll(".pbm-m-objet"),
    ).toHaveLength(1);
  });
});

describe("critère n°3 (à l'écran) — le pile ou face ne révèle rien avant la fin", () => {
  it("la pose finale attend la révélation, et la révélation n'est pas à zéro", () => {
    const effet = effetMoment(moment("piece", { objets: 2, piece: { pieces: 2, faces: 1 } }));
    render(<EffetMomentCle effet={effet} />);
    const scene = screen.getByTestId("fx-moment");
    expect(scene.style.getPropertyValue("--pbm-m-revelation")).toBe(`${effet.revelationA}ms`);
    expect(effet.revelationA).toBeGreaterThan(0);
    const pieces = Array.from(scene.querySelectorAll<HTMLElement>('[data-objet="piece"]'));
    expect(pieces).toHaveLength(2);
    expect(pieces.map((p) => p.getAttribute("data-face"))).toEqual(["face", "pile"]);
  });

  it("deux lancers opposés produisent un DOM identique, à la pose finale près", () => {
    const rendu = (faces: number) => {
      const { container, unmount } = render(
        <EffetMomentCle
          effet={effetMoment(moment("piece", { objets: 2, piece: { pieces: 2, faces } }))}
        />,
      );
      const html = (container.firstChild as HTMLElement).outerHTML.replace(
        /data-face="(face|pile)"/g,
        "data-face",
      );
      unmount();
      return html;
    };
    // Le balisage, les durées, les retards : tout est identique. Seul l'attribut de pose finale
    // diffère — et le CSS ne le rend visible qu'à `--pbm-m-revelation`.
    expect(rendu(2)).toBe(rendu(0));
  });

  it("un genre sans pièce ne porte aucune pose finale", () => {
    render(<EffetMomentCle effet={effetMoment(moment("evolution"))} />);
    expect(
      screen.getByTestId("fx-moment").querySelectorAll("[data-face]"),
    ).toHaveLength(0);
  });
});

describe("EffetMomentCle — la version réduite", () => {
  it.each(GENRES_MOMENT)("%s : immobile, annoncée, et complète", (genre) => {
    render(<EffetMomentCle effet={effetMoment(moment(genre), { reduit: true })} />);
    const badge = screen.getByTestId("fx-moment-reduit");
    // Rien ne bouge : aucune couche, aucun objet.
    expect(badge.querySelectorAll(".pbm-m-couche")).toHaveLength(0);
    expect(badge.querySelectorAll(".pbm-m-objet")).toHaveLength(0);
    // Mais l'information est entière, et elle est ANNONCÉE : ici le badge est le seul canal.
    expect(badge.getAttribute("role")).toBe("img");
    expect(badge.getAttribute("aria-label")).toBe(
      effetMoment(moment(genre), { reduit: true }).phrase,
    );
    expect(screen.queryByTestId("fx-moment")).toBeNull();
  });
});

describe("CoucheAnimation — un moment REMPLACE la pastille", () => {
  const animation = {
    cle: "1:0",
    numero: 1,
    rang: 0,
    type: "ko",
    effet: "ko",
    duree: 600,
    cible: "i-1",
    camp: "moi" as const,
    resume: false,
    nombre: 1,
    typage: null,
  };

  it("affiche le moment et retire la pastille", () => {
    render(
      <CoucheAnimation
        animation={animation}
        duree={600}
        moment={effetMoment(moment("ko"))}
        onSauter={() => {}}
      />,
    );
    expect(screen.getByTestId("anim-moment")).toBeTruthy();
    // Deux fois la même information au même endroit, c'est une occlusion de plus pour rien.
    expect(screen.queryByTestId("anim-pastille")).toBeNull();
  });

  it("garde la pastille quand il n'y a pas de moment", () => {
    render(<CoucheAnimation animation={animation} duree={600} />);
    expect(screen.getByTestId("anim-pastille")).toBeTruthy();
    expect(screen.queryByTestId("anim-moment")).toBeNull();
  });

  it("se joue — et se coupe — même sans animation du socle", () => {
    // `main_revelee` et `mise_en_place_revelee` n'ont AUCUN effet au registre du socle : le moment
    // se jouerait donc seul. Sans ce chemin, les animations les plus longues auraient été les
    // seules qu'on ne pouvait pas couper.
    const sauter = vi.fn();
    render(
      <CoucheAnimation
        animation={null}
        duree={0}
        moment={effetMoment(moment("mise-en-place"))}
        onSauter={sauter}
      />,
    );
    expect(screen.getByTestId("anim-moment")).toBeTruthy();
    fireEvent.click(screen.getByTestId("anim-sauter"));
    expect(sauter).toHaveBeenCalledTimes(1);
  });

  it("ne rend rien quand il n'y a ni animation, ni moment, ni effet d'arène", () => {
    const { container } = render(<CoucheAnimation animation={null} duree={0} onSauter={() => {}} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("useFileMoments — critère n°1 à l'écran : les quatre moments d'un double K.O.", () => {
  it("les fait défiler l'un après l'autre, et le dernier ne manque pas", () => {
    render(<Temoin liste={DOUBLE_KO} />);
    const vus: string[] = [];
    // Trois moments attendent derrière le premier : la rafale est donc comprimée (mais jamais
    // réduite à zéro — c'est ce qui ferait perdre un moment).
    expect(screen.getByTestId("attente").textContent).toBe("3");
    for (let i = 0; i < 4; i += 1) {
      vus.push(screen.getByTestId("cle").textContent ?? "");
      act(() => {
        vi.advanceTimersByTime(1600);
      });
    }
    expect(vus).toEqual(["1:0:ko", "1:0:recompense", "1:1:ko", "1:1:recompense"]);
    expect(screen.getByTestId("genre").textContent).toBe("aucun");
    expect(screen.getByTestId("attente").textContent).toBe("0");
  });

  it("« passer » enchaîne sur le moment suivant sans en perdre", () => {
    render(<Temoin liste={DOUBLE_KO} />);
    expect(screen.getByTestId("cle").textContent).toBe("1:0:ko");
    fireEvent.click(screen.getByTestId("passer"));
    expect(screen.getByTestId("cle").textContent).toBe("1:0:recompense");
    fireEvent.click(screen.getByTestId("passer"));
    expect(screen.getByTestId("cle").textContent).toBe("1:1:ko");
  });

  it("« vider » jette tout, et une rediffusion ne rejoue rien", () => {
    const { rerender } = render(<Temoin liste={DOUBLE_KO} />);
    fireEvent.click(screen.getByTestId("vider"));
    expect(screen.getByTestId("genre").textContent).toBe("aucun");
    // Le serveur rediffuse le même coup : l'écran ne doit pas repartir dans le film.
    rerender(<Temoin liste={[...DOUBLE_KO]} />);
    expect(screen.getByTestId("genre").textContent).toBe("aucun");
  });

  it("n'attend pas la vue pour exister, mais n'invente pas de camp sans destinataire", () => {
    render(<Temoin liste={DOUBLE_KO} pour="" />);
    expect(screen.getByTestId("genre").textContent).toBe("aucun");
  });

  it("en animations réduites, le moment existe quand même — immobile", () => {
    poserReducedMotion(true);
    render(<Temoin liste={DOUBLE_KO} />);
    // Couper les animations ne doit pas vouloir dire ne plus savoir qu'un K.O. a eu lieu.
    expect(screen.getByTestId("genre").textContent).toBe("ko");
  });
});
