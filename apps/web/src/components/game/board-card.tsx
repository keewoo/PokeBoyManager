"use client";

import { useRef } from "react";

import { cn } from "@/lib/utils";
import { nombreCompteurs, styleElement, visuelEtat } from "@/lib/game/indicateurs";
import type { VueCarte, VuePokemon } from "@/lib/game/plateau";

/**
 * Carte du plateau : la **surface** d'une carte (lot `j-plateau-layout`) et ses **indicateurs**
 * d'état (lot `j-plateau-etat-visuel`), à deux tailles.
 *
 * - `"plateau"` : telle qu'elle tient dans l'arène, dimensionnée en `em` qui suivent la taille du
 *   conteneur (voir `.pbm-arena` dans `globals.css`) — minuscule sur un téléphone en paysage, d'où
 *   le zoom.
 * - `"zoom"` : agrandie et **lisible sans pincer l'écran**, à une taille en `rem` indépendante.
 *
 * Les indicateurs (PV restants, compteurs de dégâts, énergies typées, Outil, états spéciaux) se
 * lisent **tels quels** sur la vue projetée par le serveur : aucune règle n'est rejouée ici
 * (« l'interface ne décide de rien »). L'image réelle et le détail des attaques restent le lot aval
 * `j-rendu-carte` : on ne fabrique pas ici des attaques qu'on n'a pas (D9).
 */
export type TailleCarte = "plateau" | "zoom";

/** Props de {@link BoardCard} : la carte à poser, son Pokémon porteur éventuel, la taille, et les
 * accroches d'interaction (zoom, mise en évidence, cible illuminée) — toutes pilotées par le parent. */
export type BoardCardProps = {
  carte: VueCarte;
  /** Le Pokémon porteur, quand la carte est un Pokémon en jeu : porte énergies, dégâts, PV, états. */
  pokemon?: VuePokemon;
  taille?: TailleCarte;
  etiquette?: string;
  className?: string;
  /** Met la carte en évidence (halo) : le Pokémon qui vient d'agir (attaque, évolution…). */
  miseEnEvidence?: boolean;
  /**
   * Signale un survol / focus / maintien long : le parent (plateau) ouvre le zoom. Reçoit la carte,
   * puis `null` quand le survol se termine. Absent → la carte n'ouvre pas de zoom (ex. la carte déjà
   * dans le zoom lui-même).
   */
  onPeek?: (carte: VueCarte | null) => void;
  /**
   * Illumine la carte comme **cible valide** d'un coup en préparation (lot
   * `j-plateau-interactions`) : elle devient cliquable et zone de dépôt (glisser-déposer). La
   * légalité vient du serveur ; l'écran ne fait que la rendre visible et saisissable.
   */
  illumine?: boolean;
  /** Choisit cette carte comme cible (tap, Entrée, ou dépôt d'un glisser) : signalé au plateau. */
  onActiver?: () => void;
};

/** Durée d'un maintien (ms) avant que le zoom s'ouvre au doigt — assez court pour être naturel,
 * assez long pour ne pas se déclencher sur un simple contact. */
const MAINTIEN_MS = 350;

/**
 * Les indicateurs d'état d'un Pokémon en jeu, posés sur sa carte comme sur une vraie table.
 *
 * Chaque repère **double la couleur d'un signe** (abréviation de type, icône d'état, chiffre de PV)
 * pour rester lisible en cas de daltonisme — critère d'acceptation du lot. Les **PV restants** sont
 * affichés en plus des compteurs de dégâts : l'enfant n'a pas à faire le calcul mental, et comme ils
 * viennent du serveur (seuil de K.O. − dégâts), ils restent exacts même avec un Outil qui ajoute des
 * PV (le risque nommé : afficher des dégâts « soustraits » mentirait).
 */
function Indicateurs({ pokemon, zoom }: { pokemon: VuePokemon; zoom: boolean }) {
  const degats = pokemon.compteurs_degats;
  const compteurs = nombreCompteurs(degats);
  const taillePv = zoom ? "text-sm" : "text-[0.55em]";
  const taillePastille = zoom ? "h-5 min-w-5 text-xs" : "h-[1.15em] min-w-[1.15em] text-[0.5em]";

  return (
    <>
      {/* PV restants + compteurs de dégâts, en haut (comme les jetons posés sur la carte). */}
      <span className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-[0.15em]">
        {degats > 0 ? (
          <span
            className={cn(
              "flex items-center gap-[0.15em] rounded-[0.3em] bg-[rgba(226,59,59,0.92)] px-[0.3em] font-mono font-bold leading-none text-white",
              taillePv,
            )}
            aria-label={`${degats} dégâts (${compteurs} compteur${compteurs > 1 ? "s" : ""})`}
          >
            <span aria-hidden>💢</span>
            {degats}
          </span>
        ) : (
          <span />
        )}
        {typeof pokemon.pv_restants === "number" && (
          <span
            className={cn(
              "flex items-center gap-[0.15em] rounded-[0.3em] bg-[rgba(10,20,10,0.85)] px-[0.3em] font-mono font-bold leading-none text-[#8FE388]",
              taillePv,
            )}
            data-testid="pv-restants"
            aria-label={`PV restants : ${pokemon.pv_restants}${
              typeof pokemon.pv_max === "number" ? ` sur ${pokemon.pv_max}` : ""
            }`}
          >
            <span aria-hidden>❤️</span>
            {pokemon.pv_restants}
            {typeof pokemon.pv_max === "number" && (
              <span className="opacity-70" aria-hidden>
                /{pokemon.pv_max}
              </span>
            )}
          </span>
        )}
      </span>

      {/* États spéciaux : une icône par état, nommée (l'orientation de la carte double le signal). */}
      {pokemon.etats_speciaux.length > 0 && (
        <span
          className="pointer-events-none absolute left-[0.15em] top-1/2 flex -translate-y-1/2 flex-col gap-[0.1em]"
          data-testid="etats-speciaux"
        >
          {pokemon.etats_speciaux.map((cle) => {
            const v = visuelEtat(cle);
            return (
              <span
                key={cle}
                className={cn(
                  "grid place-items-center rounded-full bg-[rgba(0,0,0,0.6)] leading-none",
                  taillePastille,
                )}
                role="img"
                aria-label={v.label}
                title={v.label}
              >
                {v.icone}
              </span>
            );
          })}
        </span>
      )}

      {/* Énergies attachées (typées) et Outil, en bas — empilés comme sur la table. */}
      <span className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between gap-[0.2em] p-[0.15em]">
        {pokemon.energies.length > 0 && (
          <span
            className="flex flex-wrap gap-[0.12em]"
            aria-label={`Énergies : ${pokemon.energies
              .map((e) => styleElement(e.type).label)
              .join(", ")}`}
          >
            {pokemon.energies.map((e) => {
              const s = styleElement(e.type);
              return (
                <span
                  key={e.instance_id}
                  className={cn(
                    "grid place-items-center rounded-full font-bold leading-none",
                    taillePastille,
                  )}
                  style={{ backgroundColor: s.couleur, color: s.texte }}
                  title={s.label}
                  aria-hidden
                >
                  {s.abbr}
                </span>
              );
            })}
          </span>
        )}
        {pokemon.outil && (
          <span
            className={cn(
              "flex items-center gap-[0.1em] rounded-[0.3em] bg-[rgba(157,0,255,0.85)] px-[0.25em] font-bold leading-none text-white",
              zoom ? "text-xs" : "text-[0.5em]",
            )}
            aria-label={`Outil : ${styleElement(pokemon.outil.type).label}`}
          >
            <span aria-hidden>🔧</span>
            <span aria-hidden>{styleElement(pokemon.outil.type).abbr}</span>
          </span>
        )}
      </span>
    </>
  );
}

/**
 * Rend la carte (surface + indicateurs) et câble les gestes : survol/focus/maintien long ouvrent le
 * zoom (`onPeek`), un état « cible illuminée » (`illumine`) la rend cliquable, focusable et zone de
 * dépôt. Aucune règle ici : la carte affiche ce que la vue projetée porte, le parent décide du reste.
 */
export function BoardCard({
  carte,
  pokemon,
  taille = "plateau",
  etiquette,
  className,
  miseEnEvidence,
  onPeek,
  illumine,
  onActiver,
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

  return (
    <div
      className={cn(
        "pbm-board-card relative flex select-none flex-col items-center justify-center overflow-hidden rounded-[0.5em] border text-center",
        "border-[rgba(157,0,255,0.45)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] text-foreground",
        zoom
          ? "aspect-[63/88] w-[min(70vw,16rem)] gap-2 rounded-2xl p-3 shadow-[0_0_40px_rgba(157,0,255,0.5)]"
          : "aspect-[63/88] h-full w-full gap-[0.2em] p-[0.3em] shadow-[0_0.3em_0.7em_-0.2em_#000]",
        miseEnEvidence &&
          "ring-2 ring-gold ring-offset-1 ring-offset-transparent shadow-[0_0_0.8em_rgba(242,193,78,0.8)]",
        illumine &&
          "cursor-pointer ring-2 ring-emerald-300 ring-offset-1 ring-offset-transparent shadow-[0_0_0.8em_rgba(110,231,183,0.75)]",
        className,
      )}
      data-orientation={pokemon?.orientation ?? "normale"}
      data-mise-en-evidence={miseEnEvidence ? "" : undefined}
      role={onPeek || illumine ? "button" : undefined}
      tabIndex={onPeek || illumine ? 0 : undefined}
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
      data-illumine={illumine ? "" : undefined}
      onClick={illumine && onActiver ? onActiver : undefined}
      onKeyDown={
        illumine && onActiver
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onActiver();
              }
            }
          : undefined
      }
      onDragOver={illumine ? (e) => e.preventDefault() : undefined}
      onDrop={
        illumine && onActiver
          ? (e) => {
              e.preventDefault();
              onActiver();
            }
          : undefined
      }
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
      {pokemon && <Indicateurs pokemon={pokemon} zoom={zoom} />}
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
