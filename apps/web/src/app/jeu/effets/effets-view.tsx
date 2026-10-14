"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { useAnimationsReduites } from "@/components/game/animation-layer";
import { EffetTypeAttaque } from "@/components/game/effet-type";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";
import {
  SPECS,
  type EffetAttaque,
  type SpecType,
  type Typage,
  effetAttaque,
} from "@/lib/game/anim-types";
import { EFFETS } from "@/lib/game/animations";
import { styleElement } from "@/lib/game/indicateurs";
import { cn } from "@/lib/utils";

/**
 * La galerie des effets d'attaque typés (`/jeu/effets`, lot `j-anim-attaques-typees`).
 *
 * Elle existe pour **une** raison, qui est une exigence du lot : « faire valider le rendu par JF et
 * par Aymeric avant d'industrialiser les dix types ». Les faire valider sur une vraie partie
 * demanderait d'avoir sous la main un Pokémon de chacun des onze types, avec la bonne faiblesse, la
 * bonne résistance et un pile ou face perdu — autant dire jamais. Ici tout se rejoue d'un clic, et
 * c'est le **même** code que le plateau : `effetAttaque` et `EffetTypeAttaque`, sans rien
 * reproduire. Une galerie qui redessinerait les effets à sa façon ne vaudrait aucune validation.
 *
 * Elle respecte le réglage « animations réduites » exactement comme le plateau
 * ({@link useAnimationsReduites}) : si JF le coupe, il voit ici ce qu'un enfant qui l'a coupé verra
 * en partie — c'est aussi ça qu'il doit pouvoir valider.
 *
 * Aucune donnée de joueur n'est lue : la page ne montre que des effets. Le droit d'accès au jeu
 * (D11) y est quand même contrôlé, comme sur toutes les routes `/jeu`.
 */

/** Les six situations qu'on donne à valider : trois forces, les deux modificateurs, un ratage. */
const SITUATIONS: { cle: string; libelle: string; typage: Omit<Typage, "type"> }[] = [
  {
    cle: "legere",
    libelle: "Petite attaque",
    typage: { degats: 30, faiblesse: false, resistance: false, echec: false },
  },
  {
    cle: "nette",
    libelle: "Attaque moyenne",
    typage: { degats: 100, faiblesse: false, resistance: false, echec: false },
  },
  {
    cle: "violente",
    libelle: "Grosse attaque",
    typage: { degats: 200, faiblesse: false, resistance: false, echec: false },
  },
  {
    cle: "faiblesse",
    libelle: "Faiblesse (×2)",
    typage: { degats: 120, faiblesse: true, resistance: false, echec: false },
  },
  {
    cle: "resistance",
    libelle: "Résistance (−30)",
    typage: { degats: 30, faiblesse: false, resistance: true, echec: false },
  },
  {
    cle: "echec",
    libelle: "Attaque ratée",
    typage: { degats: 0, faiblesse: false, resistance: false, echec: true },
  },
];

/** La situation par défaut : une attaque moyenne, celle qu'on voit le plus souvent en partie. */
const SITUATION_DEFAUT = "nette";

/**
 * La durée que le socle accorde à un `degats` — on la **lit** dans le registre au lieu de la
 * recopier, pour que la galerie montre la durée réelle du plateau et pas une durée de démonstration.
 */
const DUREE_DEGATS = EFFETS.degats?.duree ?? 420;

/** Une carte de démonstration : la boîte d'une carte du plateau, sans vraie carte dedans. */
function Vignette({
  spec,
  effet,
  degats,
  generation,
}: {
  spec: SpecType;
  effet: EffetAttaque | null;
  /** Les dégâts de la situation montrée — affichés comme sur une vraie carte. */
  degats: number;
  generation: number;
}) {
  const style = styleElement(spec.code);
  return (
    <div
      data-testid={`fx-demo-${spec.cle}`}
      data-fx-geste={effet?.gesteCarte && effet.gesteCarte !== "aucun" ? effet.gesteCarte : undefined}
      className="pbm-board-card relative mx-auto flex aspect-[63/88] w-[7.5rem] select-none flex-col items-center justify-center gap-1 overflow-hidden rounded-[0.5em] border border-[rgba(157,0,255,0.45)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] p-2 text-center text-[1.4rem]"
      style={
        effet?.anime
          ? ({ "--pbm-fx-duree": `${effet.duree}ms` } as React.CSSProperties)
          : undefined
      }
    >
      <span
        className="rounded-[0.3em] px-[0.3em] py-[0.05em] text-[0.45em] font-bold leading-none"
        style={{ backgroundColor: style.couleur, color: style.texte }}
        aria-hidden
      >
        {style.abbr}
      </span>
      <span className="text-[0.4em] font-bold leading-tight text-gold">{spec.libelle}</span>
      <EffetTypeAttaque effet={effet} cle={`${spec.cle}:${generation}`} />
      {/* Les repères du plateau, à leur vraie place : c'est l'autre chose à valider — l'effet ne
          doit JAMAIS les cacher. Ils sont rendus APRÈS l'effet, donc au-dessus, comme sur la
          carte réelle (`board-card.tsx`). */}
      <span className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-[0.15em]">
        <span className="rounded-[0.3em] bg-[rgba(226,59,59,0.92)] px-[0.3em] font-mono text-[0.42em] font-bold leading-none text-white">
          💢 {degats}
        </span>
        <span className="rounded-[0.3em] bg-[rgba(10,20,10,0.85)] px-[0.3em] font-mono text-[0.42em] font-bold leading-none text-[#8FE388]">
          ❤️ 120
        </span>
      </span>
    </div>
  );
}

export function EffetsView() {
  const [refuse, setRefuse] = useState(false);
  const [erreurProfil, setErreurProfil] = useState<string | null>(null);
  const [situation, setSituation] = useState(SITUATION_DEFAUT);
  // Change à chaque relance : c'est la clé qui redémarre les animations CSS (le navigateur ne
  // rejoue pas une animation déjà terminée sur un nœud réutilisé).
  const [generation, setGeneration] = useState(1);
  const reduit = useAnimationsReduites();

  // Autorité d'accès : `game_access` est lu côté serveur. Faux → page inexistante. Un échec de
  // lecture n'est PAS un refus : « je n'ai pas pu savoir » et « tu n'as pas le droit » diffèrent.
  useEffect(() => {
    let actif = true;
    getProfile()
      .then((profil) => {
        if (!actif) return;
        if (!profil.game_access) setRefuse(true);
      })
      .catch((cause) => {
        if (actif) {
          setErreurProfil(cause instanceof ApiError ? cause.message : "Chargement impossible.");
        }
      });
    return () => {
      actif = false;
    };
  }, []);

  const rejouer = useCallback((cle: string) => {
    setSituation(cle);
    setGeneration((g) => g + 1);
  }, []);

  if (refuse) notFound();

  const choisie = SITUATIONS.find((s) => s.cle === situation) ?? SITUATIONS[1]!;

  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-8" data-testid="fx-galerie">
      <h1 className="font-heading text-2xl font-extrabold">Les effets d&apos;attaque</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Chaque type d&apos;énergie a son effet sur la carte d&apos;en face. Choisis une situation,
        puis regarde&nbsp;: c&apos;est exactement ce que le plateau joue en partie — même code, même
        durée.
      </p>

      {erreurProfil && (
        <div className="mt-4">
          <FormNotice variant="error">{erreurProfil}</FormNotice>
        </div>
      )}

      {reduit && (
        <p
          className="mt-4 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-xs text-muted-foreground"
          data-testid="fx-note-reduit"
          role="status"
        >
          Tu as coupé les animations (ou ton appareil les coupe). Tu vois donc la version
          réduite&nbsp;: rien ne bouge, et chaque effet dit en texte ce qu&apos;il aurait montré.
          C&apos;est ce qu&apos;un joueur qui les a coupées voit en partie.
        </p>
      )}

      <section className="mt-6" aria-labelledby="titre-situations">
        <h2 id="titre-situations" className="font-heading text-lg font-bold">
          La situation à montrer
        </h2>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Situation à montrer">
          {SITUATIONS.map((s) => (
            <Button
              key={s.cle}
              type="button"
              variant={s.cle === situation ? "default" : "outline"}
              data-testid={`fx-situation-${s.cle}`}
              aria-pressed={s.cle === situation}
              onClick={() => rejouer(s.cle)}
            >
              {s.libelle}
            </Button>
          ))}
        </div>
        <Button
          type="button"
          className="mt-3"
          variant="outline"
          data-testid="fx-rejouer"
          onClick={() => rejouer(situation)}
        >
          Rejouer les onze effets
        </Button>
      </section>

      <ul className="mt-8 grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-4">
        {Object.values(SPECS).map((spec) => {
          const effet = effetAttaque(
            { type: spec.code, ...choisie.typage },
            { duree: DUREE_DEGATS, reduit },
          );
          return (
            <li key={spec.cle} className="flex flex-col gap-2">
              <Vignette
                spec={spec}
                effet={effet}
                degats={choisie.typage.degats}
                generation={generation}
              />
              <p className="text-center text-xs text-muted-foreground">{spec.geste}</p>
              <Button
                type="button"
                variant="ghost"
                className={cn("text-xs")}
                data-testid={`fx-jouer-${spec.cle}`}
                onClick={() => rejouer(situation)}
              >
                Rejouer {spec.libelle}
              </Button>
            </li>
          );
        })}
      </ul>

      <p className="mt-10 text-xs text-muted-foreground">
        Pour couper les animations partout, c&apos;est dans{" "}
        <Link href="/jeu/confort" className="underline">
          Confort de jeu
        </Link>
        .
      </p>
    </main>
  );
}
