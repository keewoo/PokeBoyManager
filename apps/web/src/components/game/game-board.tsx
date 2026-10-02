"use client";

import { useCallback, useState } from "react";

import { BoardCard, EmptySlot } from "@/components/game/board-card";
import { CardZoom } from "@/components/game/card-zoom";
import { StatutConnexion } from "@/components/game/connection-status";
import { ZoneCachee, ZonePublique } from "@/components/game/zone-consultation";
import { cn } from "@/lib/utils";
import type { EtatConnexion } from "@/lib/game/realtime";
import {
  BANC_MAX,
  RECOMPENSES_MAX,
  bancAvecVides,
  carteDessus,
  estMonTour,
  nombreEnMain,
  separerCamps,
  type VueCarte,
  type VueJoueur,
  type VuePartie,
  type VuePokemon,
} from "@/lib/game/plateau";

/**
 * Le plateau de jeu (lot `j-plateau-layout`) : les deux camps, du grand écran au téléphone.
 *
 * La difficulté est **spatiale**, pas graphique : neuf zones par joueur (actif, banc de cinq, main,
 * pioche, défausse, six récompenses, Stade partagé) doivent tenir sur un écran de téléphone en
 * paysage sans qu'on perde de vue l'essentiel. L'arène se met à l'échelle via des `em` qui suivent la
 * plus petite dimension du conteneur (`.pbm-arena`, `globals.css`) : les cartes rétrécissent sur un
 * petit écran plutôt que de déborder, et le zoom (`CardZoom`) rend le détail lisible.
 *
 * L'interface ne décide de rien : tout vient de la vue projetée par le serveur (`VuePartie`). Les
 * zones cachées (pioche, récompenses, main adverse) n'affichent qu'un **compteur** — leur contenu
 * n'existe pas côté client.
 */
export type GameBoardProps = {
  vue: VuePartie;
  /** État de la connexion temps réel, affiché en surimpression (rien quand elle est directe). */
  etatConnexion?: EtatConnexion;
};

/** Ouvre le zoom sur une carte (avec son Pokémon porteur s'il y en a un), ou le ferme avec `null`. */
type ZoomFn = (carte: VueCarte | null, pokemon?: VuePokemon) => void;

/** Ce que le zoom doit montrer : la carte, et le Pokémon porteur s'il y en a un (énergies, dégâts). */
type Agrandie = { carte: VueCarte; pokemon?: VuePokemon };

/** Les six pastilles de récompenses : pleines pour celles restant à prendre, vides pour les prises. */
function Recompenses({ restantes, pour }: { restantes: number; pour: string }) {
  return (
    <span
      className="inline-grid grid-cols-3 gap-[0.15em]"
      aria-label={`${pour} : ${restantes} récompense(s) sur ${RECOMPENSES_MAX}`}
    >
      {Array.from({ length: RECOMPENSES_MAX }, (_, i) => (
        <i
          key={i}
          aria-hidden
          className={cn(
            "aspect-[63/88] w-[1.1em] rounded-[0.15em]",
            i < restantes
              ? "bg-[linear-gradient(150deg,#FFE08A,#C98A12)] shadow-[0_0_0.4em_rgba(242,193,78,0.5)]"
              : "border border-dashed border-[rgba(255,255,255,0.3)]",
          )}
        />
      ))}
    </span>
  );
}

/** Le bandeau haut : les deux joueurs, qui a le trait (halo), leurs récompenses et leur main. */
function VsBar({
  moi,
  adversaire,
  monTour,
}: {
  moi: VueJoueur;
  adversaire: VueJoueur;
  monTour: boolean;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-[0.8em] px-[1.2em] py-[0.6em]">
      <div className={cn("flex min-w-0 items-center gap-[0.5em]", !monTour && "font-bold")}>
        <span
          className={cn(
            "grid h-[2.2em] w-[2.2em] place-items-center rounded-full bg-[conic-gradient(from_210deg,#F2C14E,#7FE3B0,#F2C14E)] font-heading text-[0.8em] font-extrabold text-[#08150F]",
            !monTour && "shadow-[0_0_0_0.14em_#F2C14E,0_0_1em_rgba(242,193,78,0.6)]",
          )}
          aria-hidden
        >
          AD
        </span>
        <span className="truncate font-heading text-[0.95em] font-bold">Adversaire</span>
        <Recompenses restantes={adversaire.recompenses_nombre} pour="Adversaire" />
        <span
          className="font-mono text-[0.75em] text-muted-foreground"
          aria-label={`Main adverse : ${nombreEnMain(adversaire)} carte(s)`}
        >
          ✋{nombreEnMain(adversaire)}
        </span>
      </div>
      <span className="font-pixel text-[0.7em] text-gold">VS</span>
      <div className={cn("flex min-w-0 items-center justify-end gap-[0.5em]", monTour && "font-bold")}>
        <Recompenses restantes={moi.recompenses_nombre} pour="Toi" />
        <span className="truncate font-heading text-[0.95em] font-bold">Toi</span>
        <span
          className={cn(
            "grid h-[2.2em] w-[2.2em] place-items-center rounded-full bg-[conic-gradient(from_210deg,#F2C14E,#7FE3B0,#F2C14E)] font-heading text-[0.8em] font-extrabold text-[#08150F]",
            monTour && "shadow-[0_0_0_0.14em_#F2C14E,0_0_1em_rgba(242,193,78,0.6)]",
          )}
          aria-hidden
        >
          JF
        </span>
      </div>
    </div>
  );
}

/** Un holder : un contenu surmonté d'une étiquette, comme dans la maquette du jeu. */
function Holder({ lab, children }: { lab: string; children: React.ReactNode }) {
  return (
    <span className="grid justify-items-center gap-[0.3em]">
      {children}
      <span className="text-[0.55em] uppercase tracking-[0.1em] text-[#9FD9BC]">{lab}</span>
    </span>
  );
}

// --- Fonctions de rendu (appelées directement, jamais comme `<Composant/>` : un composant défini
// dans le corps de `GameBoard` serait remonté à chaque rendu — l'état de survol serait perdu). ---

/** Une case d'actif : le Pokémon (dominant) ou un emplacement vide. */
function caseActif(
  joueur: VueJoueur,
  etiquette: string,
  largeur: string,
  onZoom: ZoomFn,
): React.ReactNode {
  const dessus = joueur.actif ? carteDessus(joueur.actif) : null;
  if (!joueur.actif || !dessus) {
    return <EmptySlot etiquette={etiquette} className={largeur} />;
  }
  return (
    <span className={largeur}>
      <BoardCard
        carte={dessus}
        pokemon={joueur.actif}
        etiquette={etiquette}
        onPeek={(c) => onZoom(c, joueur.actif ?? undefined)}
      />
    </span>
  );
}

/** Le banc d'un joueur : cinq cases fixes, Pokémon ou vides. */
function banc(
  joueur: VueJoueur,
  etiquette: string,
  largeur: string,
  onZoom: ZoomFn,
): React.ReactNode {
  return (
    <div className="flex justify-center gap-[0.5em]">
      {bancAvecVides(joueur, BANC_MAX).map((p, i) => {
        const dessus = p ? carteDessus(p) : null;
        return p && dessus ? (
          <span key={i} className={largeur}>
            <BoardCard
              carte={dessus}
              pokemon={p}
              etiquette={`${etiquette} ${i + 1}`}
              onPeek={(c) => onZoom(c, p)}
            />
          </span>
        ) : (
          <EmptySlot key={i} etiquette="banc" className={largeur} />
        );
      })}
    </div>
  );
}

export function GameBoard({ vue, etatConnexion }: GameBoardProps) {
  const { moi, adversaire } = separerCamps(vue);
  const monTour = estMonTour(vue);
  const [zoom, setZoom] = useState<Agrandie | null>(null);
  const onZoom = useCallback<ZoomFn>(
    (carte, pokemon) => setZoom(carte ? { carte, pokemon } : null),
    [],
  );

  return (
    <section data-testid="plateau" className="pbm-plateau relative flex w-full flex-col gap-2">
      <div className="pbm-rotate-hint" aria-hidden>
        Tourne ton téléphone en paysage pour mieux voir le plateau.
      </div>

      <div className="pbm-arena relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl bg-[radial-gradient(70%_80%_at_50%_50%,#0E2A1E,#06120B)] text-[#EAF3EE] shadow-[0_20px_50px_-30px_rgba(0,0,0,0.9)]">
        {etatConnexion && (
          <div className="absolute left-1/2 top-2 z-10 -translate-x-1/2">
            <StatutConnexion etat={etatConnexion} />
          </div>
        )}

        <VsBar moi={moi} adversaire={adversaire} monTour={monTour} />

        {/* Le champ : rang adverse, ligne centrale (Stade partagé), rang joueur, puis son banc. */}
        <div className="grid min-h-0 flex-1 content-between gap-[0.5em] px-[1.5em] py-[0.5em]">
          {/* Rang adverse */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-[1em]">
            <span className="justify-self-start">
              <Holder lab="banc adverse">{banc(adversaire, "banc adverse", "w-[4.6875em]", onZoom)}</Holder>
            </span>
            {caseActif(adversaire, "Actif adverse", "w-[6.875em]", onZoom)}
            <span className="flex justify-self-end gap-[0.6em]">
              <Holder lab="pioche">
                <ZoneCachee titre="pioche" nombre={adversaire.pioche_nombre} />
              </Holder>
              <Holder lab="défausse">
                <ZonePublique titre="défausse adverse" cartes={adversaire.defausse} />
              </Holder>
            </span>
          </div>

          {/* Ligne centrale : le Stade est partagé, posé au milieu. */}
          <div className="flex items-center gap-[0.8em] text-[0.6em] uppercase tracking-[0.14em] text-[#9FD9BC] opacity-75">
            <span className="h-px flex-1 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.35),transparent)]" />
            {vue.stade ? (
              <span className="w-[4.6875em]">
                <BoardCard carte={vue.stade} etiquette="Stade" onPeek={(c) => onZoom(c)} />
              </span>
            ) : (
              <span className="normal-case">Stade (aucun)</span>
            )}
            <span className="h-px flex-1 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.35),transparent)]" />
          </div>

          {/* Rang joueur */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-[1em]">
            <span className="justify-self-start">
              <Holder lab="récompenses">
                <Recompenses restantes={moi.recompenses_nombre} pour="Toi" />
              </Holder>
            </span>
            {caseActif(moi, "Mon actif", "w-[9.0625em]", onZoom)}
            <span className="flex justify-self-end gap-[0.6em]">
              <Holder lab="pioche">
                <ZoneCachee titre="pioche" nombre={moi.pioche_nombre} />
              </Holder>
              <Holder lab="défausse">
                <ZonePublique titre="ma défausse" cartes={moi.defausse} />
              </Holder>
            </span>
          </div>

          {/* Mon banc */}
          {banc(moi, "Mon banc", "w-[6.5625em]", onZoom)}
        </div>
      </div>

      {/* Ma main : hors de l'arène, toujours accessible (critère « la main reste accessible »). */}
      <Main moi={moi} onZoom={onZoom} />

      <CardZoom carte={zoom?.carte ?? null} pokemon={zoom?.pokemon} onClose={() => setZoom(null)} />
    </section>
  );
}

/**
 * La main du joueur, en éventail compact. Les cartes se chevauchent (`-ml`) pour tenir en largeur
 * sur un téléphone sans jamais provoquer de défilement horizontal de la page ; la carte survolée se
 * relève. Seules **mes** identités y figurent — la main adverse n'est qu'un compteur (`VsBar`).
 */
function Main({ moi, onZoom }: { moi: VueJoueur; onZoom: ZoomFn }) {
  const main = moi.main ?? [];
  return (
    <div
      className="flex min-h-[4.5rem] items-end justify-center overflow-x-auto px-2 pt-2"
      data-testid="main-joueur"
      aria-label={`Ta main : ${main.length} carte(s)`}
    >
      {main.length === 0 ? (
        <span className="pb-4 text-sm italic text-muted-foreground">Main vide.</span>
      ) : (
        main.map((c, i) => (
          <div
            key={c.instance_id}
            className="h-[4.25rem] w-[3rem] shrink-0 origin-bottom transition-transform hover:z-10 hover:-translate-y-2 hover:scale-110"
            style={{ marginLeft: i === 0 ? 0 : "-0.75rem" }}
          >
            <BoardCard carte={c} etiquette="Main" onPeek={(peeked) => onZoom(peeked)} />
          </div>
        ))
      )}
    </div>
  );
}
