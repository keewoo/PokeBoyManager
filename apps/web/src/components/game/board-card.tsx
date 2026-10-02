"use client";

import { useRef } from "react";

import { cn } from "@/lib/utils";
import type { VueCarte, VuePokemon } from "@/lib/game/plateau";

/**
 * Carte du plateau (lot `j-plateau-layout`) : la **surface** d'une carte, à deux tailles.
 *
 * - `"plateau"` : telle qu'elle tient dans l'arène, dimensionnée en `em` qui suivent la taille du
 *   conteneur (voir `.pbm-arena` dans `globals.css`) — minuscule sur un téléphone en paysage, d'où
 *   le zoom.
 * - `"zoom"` : agrandie et **lisible sans pincer l'écran** (critère du lot), à une taille en `rem`
 *   indépendante du conteneur.
 *
 * Ce qui s'affiche ici est volontairement un **repère de disposition** : la référence de la carte et
 * les pastilles d'état minimales portées par la vue. L'image réelle (ma photo ou l'image officielle)
 * et le détail jouable (attaques, coûts) sont le lot aval `j-rendu-carte` ; le rendu fin des dégâts,
 * énergies et états est `j-plateau-etat-visuel`. On ne fabrique pas ici des attaques qu'on n'a pas
 * (D9) : le point d'extension est ce composant, pas un faux contenu.
 */
export type TailleCarte = "plateau" | "zoom";

export type BoardCardProps = {
  carte: VueCarte;
  /** Le Pokémon porteur, quand la carte est un Pokémon en jeu : porte énergies, dégâts, états. */
  pokemon?: VuePokemon;
  taille?: TailleCarte;
  etiquette?: string;
  className?: string;
  /**
   * Signale un survol / focus / maintien long : le parent (plateau) ouvre le zoom. Reçoit la carte,
   * puis `null` quand le survol se termine. Absent → la carte n'ouvre pas de zoom (ex. la carte déjà
   * dans le zoom lui-même).
   */
  onPeek?: (carte: VueCarte | null) => void;
};

/** Durée d'un maintien (ms) avant que le zoom s'ouvre au doigt — assez court pour être naturel,
 * assez long pour ne pas se déclencher sur un simple contact. */
const MAINTIEN_MS = 350;

export function BoardCard({
  carte,
  pokemon,
  taille = "plateau",
  etiquette,
  className,
  onPeek,
}: BoardCardProps) {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function ouvrir() {
    onPeek?.(carte);
  }
  function fermer() {
    onPeek?.(null);
  }
  function annulerMaintien() {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }
  function demarrerMaintien() {
    annulerMaintien();
    timer.current = setTimeout(ouvrir, MAINTIEN_MS);
  }

  const zoom = taille === "zoom";
  const nbEnergies = pokemon?.energies.length ?? 0;
  const degats = pokemon?.compteurs_degats ?? 0;

  return (
    <div
      className={cn(
        "relative flex select-none flex-col items-center justify-center overflow-hidden rounded-[0.5em] border text-center",
        "border-[rgba(157,0,255,0.45)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] text-foreground",
        zoom
          ? "aspect-[63/88] w-[min(70vw,16rem)] gap-2 rounded-2xl p-3 shadow-[0_0_40px_rgba(157,0,255,0.5)]"
          : "aspect-[63/88] h-full w-full gap-[0.2em] p-[0.3em] shadow-[0_0.3em_0.7em_-0.2em_#000]",
        className,
      )}
      data-orientation={pokemon?.orientation ?? "normale"}
      role={onPeek ? "button" : undefined}
      tabIndex={onPeek ? 0 : undefined}
      aria-label={etiquette ? `${etiquette} — ${carte.ref}` : carte.ref}
      onMouseEnter={onPeek ? ouvrir : undefined}
      onMouseLeave={
        onPeek
          ? () => {
              annulerMaintien();
              fermer();
            }
          : undefined
      }
      onFocus={onPeek ? ouvrir : undefined}
      onBlur={onPeek ? fermer : undefined}
      onPointerDown={onPeek ? demarrerMaintien : undefined}
      onPointerUp={onPeek ? annulerMaintien : undefined}
      onPointerCancel={onPeek ? annulerMaintien : undefined}
    >
      <span
        className={cn(
          "break-all font-heading font-bold leading-tight text-gold",
          zoom ? "text-lg" : "text-[0.85em]",
        )}
      >
        {carte.ref}
      </span>
      {zoom && (
        <span className="text-xs text-muted-foreground">
          Carte en jeu — l&apos;image officielle et le détail des attaques arrivent avec le rendu de
          carte.
        </span>
      )}
      {/* Pastilles minimales : un simple repère de disposition (le visuel fin est `j-plateau-etat-visuel`). */}
      {(nbEnergies > 0 || degats > 0) && (
        <span
          className={cn(
            "flex items-center justify-center gap-[0.3em] font-mono text-muted-foreground",
            zoom ? "text-sm" : "text-[0.7em]",
          )}
        >
          {nbEnergies > 0 && <span aria-label={`${nbEnergies} énergie(s)`}>⚡{nbEnergies}</span>}
          {degats > 0 && (
            <span className="text-danger" aria-label={`${degats} dégâts`}>
              ♥{degats}
            </span>
          )}
        </span>
      )}
    </div>
  );
}

/**
 * Un emplacement vide (banc, actif sans Pokémon) : un cadre en pointillés qui nomme la zone. Garde
 * la grille stable même quand une zone se vide — une table réelle a des emplacements fixes.
 */
export function EmptySlot({ etiquette, className }: { etiquette: string; className?: string }) {
  return (
    <div
      className={cn(
        "flex aspect-[63/88] items-center justify-center rounded-[0.45em] border border-dashed border-[rgba(255,255,255,0.28)] text-center text-[0.6em] uppercase tracking-[0.06em] text-muted-foreground",
        className,
      )}
    >
      {etiquette}
    </div>
  );
}
