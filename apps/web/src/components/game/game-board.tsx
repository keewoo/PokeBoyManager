"use client";

import { useCallback, useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { ActionBar } from "@/components/game/action-bar";
import { BoardCard, EmptySlot } from "@/components/game/board-card";
import { CardZoom } from "@/components/game/card-zoom";
import { StatutConnexion } from "@/components/game/connection-status";
import { ZoneCachee, ZonePublique } from "@/components/game/zone-consultation";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import {
  REPOS,
  type Evenement,
  type Selection,
  type Soumission,
  cibleParReference,
  ciblesIlluminees,
  reduire,
} from "@/lib/game/interactions";
import type { EtatConnexion } from "@/lib/game/realtime";
import {
  BANC_MAX,
  RECOMPENSES_MAX,
  bancAvecVides,
  carteDessus,
  estMonTour,
  nombreEnMain,
  separerCamps,
  type VueActionLegale,
  type VueCarte,
  type VueCible,
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
 * n'existe pas côté client. Les coups jouables aussi viennent du serveur (`actions_legales`) : l'écran
 * illumine leurs cibles et les soumet, sans réécrire aucune règle (lot `j-plateau-interactions`).
 */
export type GameBoardProps = {
  vue: VuePartie;
  /** État de la connexion temps réel, affiché en surimpression (rien quand elle est directe). */
  etatConnexion?: EtatConnexion;
  /**
   * Identité (instance de la carte de base) du Pokémon qui **vient d'agir** — mis en évidence par un
   * halo. Dérivé des événements du dernier coup ; `null`/absent quand rien n'a encore agi.
   */
  agisseur?: string | null;
  /**
   * Identité (instance de la carte de base) du Pokémon **désigné par la ligne de journal survolée**
   * (lot `j-plateau-journal`) : le plateau le met en évidence par le même halo que l'agisseur, pour
   * relier le fil des coups à l'endroit concerné. `null`/absent quand aucune ligne n'est survolée.
   */
  surligne?: string | null;
  /**
   * Joue un coup — fourni par le conteneur de partie (lot `j-plateau-interactions`). Absent, le
   * plateau reste en **lecture seule** (aucune barre d'actions, aucune cible saisissable). Doit
   * rejeter sur un refus (`ApiError` 422) dont le message porte la raison du moteur : le plateau
   * l'affiche telle quelle.
   */
  onJouer?: (action: VueActionLegale, cible: VueCible | null) => Promise<void>;
};

/** Ouvre le zoom sur une carte (avec son Pokémon porteur s'il y en a un), ou le ferme avec `null`. */
type ZoomFn = (carte: VueCarte | null, pokemon?: VuePokemon) => void;

/** Ce que le zoom doit montrer : la carte, et le Pokémon porteur s'il y en a un (énergies, dégâts). */
type Agrandie = { carte: VueCarte; pokemon?: VuePokemon };

/**
 * Le lien entre une carte du plateau et l'interaction en cours : savoir si une référence est une
 * cible illuminée, et la choisir (tap, clavier, dépôt). Absent en lecture seule. Wiring porté par le
 * lot `j-plateau-interactions` ; la légalité des cibles reste au serveur.
 */
type Interaction = {
  illumineRef: (reference: string) => boolean;
  activerRef: (reference: string) => void;
};

/** La référence (instance_id) de la carte d'un Pokémon qui est actuellement une cible illuminée, ou `undefined`. */
function refCiblePokemon(pokemon: VuePokemon, inter?: Interaction): string | undefined {
  if (!inter) return undefined;
  return pokemon.cartes.find((c) => inter.illumineRef(c.instance_id))?.instance_id;
}

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
  agisseur?: string | null,
  surligne?: string | null,
  inter?: Interaction,
): React.ReactNode {
  const dessus = joueur.actif ? carteDessus(joueur.actif) : null;
  if (!joueur.actif || !dessus) {
    return <EmptySlot etiquette={etiquette} className={largeur} />;
  }
  const refCible = refCiblePokemon(joueur.actif, inter);
  return (
    <span className={largeur}>
      <BoardCard
        carte={dessus}
        pokemon={joueur.actif}
        etiquette={etiquette}
        miseEnEvidence={estEnEvidence(joueur.actif, agisseur, surligne)}
        illumine={!!refCible}
        onActiver={refCible && inter ? () => inter.activerRef(refCible) : undefined}
        onPeek={(c) => onZoom(c, joueur.actif ?? undefined)}
      />
    </span>
  );
}

/** Vrai si ce Pokémon est celui qui vient d'agir (comparaison sur l'instance de sa carte de base). */
function estAgisseur(pokemon: VuePokemon, agisseur?: string | null): boolean {
  return !!agisseur && pokemon.cartes[0]?.instance_id === agisseur;
}

/**
 * Vrai si ce Pokémon doit porter le halo : soit il **vient d'agir** (`agisseur`), soit il est
 * **désigné par la ligne de journal survolée** (`surligne`). Les deux se comparent sur l'instance de
 * sa carte de base — le même repère relie « ce qui vient d'arriver » et « ce que dit le journal ».
 */
function estEnEvidence(pokemon: VuePokemon, agisseur?: string | null, surligne?: string | null): boolean {
  return estAgisseur(pokemon, agisseur) || estAgisseur(pokemon, surligne);
}

/** Le banc d'un joueur : cinq cases fixes, Pokémon ou vides. */
function banc(
  joueur: VueJoueur,
  etiquette: string,
  largeur: string,
  onZoom: ZoomFn,
  agisseur?: string | null,
  surligne?: string | null,
  inter?: Interaction,
): React.ReactNode {
  return (
    <div className="flex justify-center gap-[0.5em]">
      {bancAvecVides(joueur, BANC_MAX).map((p, i) => {
        const dessus = p ? carteDessus(p) : null;
        if (!p || !dessus) {
          return <EmptySlot key={i} etiquette="banc" className={largeur} />;
        }
        const refCible = refCiblePokemon(p, inter);
        return (
          <span key={i} className={largeur}>
            <BoardCard
              carte={dessus}
              pokemon={p}
              etiquette={`${etiquette} ${i + 1}`}
              miseEnEvidence={estEnEvidence(p, agisseur, surligne)}
              illumine={!!refCible}
              onActiver={refCible && inter ? () => inter.activerRef(refCible) : undefined}
              onPeek={(c) => onZoom(c, p)}
            />
          </span>
        );
      })}
    </div>
  );
}

export function GameBoard({ vue, etatConnexion, agisseur, surligne, onJouer }: GameBoardProps) {
  const { moi, adversaire } = separerCamps(vue);
  const monTour = estMonTour(vue);
  const [zoom, setZoom] = useState<Agrandie | null>(null);
  const onZoom = useCallback<ZoomFn>(
    (carte, pokemon) => setZoom(carte ? { carte, pokemon } : null),
    [],
  );

  const legales = vue.actions_legales ?? [];
  const refusees = vue.actions_refusees ?? [];

  // Interaction : la sélection vit dans un état (pour le rendu) **et** une ref (pour décider sans
  // attendre un re-rendu — c'est ce qui bloque un double-envoi sur deux clics synchrones).
  const [selection, setSelection] = useState<Selection>(REPOS);
  const selectionRef = useRef<Selection>(REPOS);
  const [verrou, setVerrou] = useState(false);
  const verrouRef = useRef(false);
  const [refus, setRefus] = useState<string | null>(null);

  const soumettre = useCallback(
    async (s: Soumission) => {
      if (!onJouer || verrouRef.current) return; // un coup déjà en vol : on ignore (anti double-envoi)
      verrouRef.current = true;
      setVerrou(true);
      setRefus(null);
      try {
        await onJouer(s.action, s.cible);
      } catch (e) {
        // Le serveur fait autorité : on affiche SA raison (message du moteur), jamais un texte inventé.
        setRefus(
          e instanceof ApiError ? e.message : "Coup impossible. Réessaie dans un instant.",
        );
      } finally {
        verrouRef.current = false;
        setVerrou(false);
      }
    },
    [onJouer],
  );

  const traiter = useCallback(
    (evt: Evenement) => {
      const r = reduire(selectionRef.current, evt);
      selectionRef.current = r.selection;
      setSelection(r.selection);
      if (r.soumission) void soumettre(r.soumission);
    },
    [soumettre],
  );

  // Pont entre une carte du plateau et la machine à états : illumination + choix d'une cible.
  const illumination = ciblesIlluminees(selection);
  const inter: Interaction | undefined = onJouer
    ? {
        illumineRef: (reference) => illumination.has(reference),
        activerRef: (reference) => {
          const cible = cibleParReference(selectionRef.current, reference);
          if (cible) traiter({ t: "choisir-cible", cible });
        },
      }
    : undefined;

  const stadeRefCible = inter && vue.stade ? vue.stade.instance_id : undefined;

  return (
    <section data-testid="plateau" className="pbm-plateau relative flex w-full flex-col gap-2">
      <div className="pbm-rotate-hint" aria-hidden>
        Tourne ton téléphone en paysage pour mieux voir le plateau.
      </div>

      {/* Conteneur de requête : il reçoit la hauteur disponible (`flex-1`) et la donne à
          l'arène via `cqh` — l'arène ne peut pas interroger sa propre taille. */}
      <div className="pbm-arena-box flex min-h-0 flex-1">
        <div className="pbm-arena relative flex min-h-0 w-full flex-1 flex-col overflow-hidden rounded-2xl bg-[radial-gradient(70%_80%_at_50%_50%,#0E2A1E,#06120B)] text-[#EAF3EE] shadow-[0_20px_50px_-30px_rgba(0,0,0,0.9)]">
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
              <Holder lab="banc adverse">{banc(adversaire, "banc adverse", "w-[4.6875em]", onZoom, agisseur, surligne, inter)}</Holder>
            </span>
            {caseActif(adversaire, "Actif adverse", "w-[6.875em]", onZoom, agisseur, surligne, inter)}
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
                <BoardCard
                  carte={vue.stade}
                  etiquette="Stade"
                  illumine={!!(stadeRefCible && inter?.illumineRef(stadeRefCible))}
                  onActiver={
                    stadeRefCible && inter?.illumineRef(stadeRefCible)
                      ? () => inter.activerRef(stadeRefCible)
                      : undefined
                  }
                  onPeek={(c) => onZoom(c)}
                />
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
            {caseActif(moi, "Mon actif", "w-[9.0625em]", onZoom, agisseur, surligne, inter)}
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
          {banc(moi, "Mon banc", "w-[6.5625em]", onZoom, agisseur, surligne, inter)}
          </div>
        </div>
      </div>

      {/* Barre d'actions + raison d'un refus : seulement quand le plateau est jouable (onJouer). */}
      {onJouer && (
        <div className="flex flex-col gap-1">
          {refus && (
            <div data-testid="refus-coup">
              <FormNotice variant="error">{refus}</FormNotice>
            </div>
          )}
          <ActionBar
            legales={legales}
            refusees={refusees}
            selection={selection}
            verrou={verrou}
            onChoisir={(action) => traiter({ t: "choisir-action", action })}
            onConfirmer={() => traiter({ t: "confirmer" })}
            onAnnuler={() => traiter({ t: "annuler" })}
          />
        </div>
      )}

      {/* Ma main : hors de l'arène, toujours accessible (critère « la main reste accessible »). */}
      <Main moi={moi} onZoom={onZoom} inter={inter} />

      <CardZoom carte={zoom?.carte ?? null} pokemon={zoom?.pokemon} onClose={() => setZoom(null)} />
    </section>
  );
}

/**
 * La main du joueur, en éventail compact. Les cartes se chevauchent (`-ml`) pour tenir en largeur
 * sur un téléphone sans jamais provoquer de défilement horizontal de la page ; la carte survolée se
 * relève. Seules **mes** identités y figurent — la main adverse n'est qu'un compteur (`VsBar`). Une
 * carte de main qui est cible d'un coup est illuminée et jouable (lot `j-plateau-interactions`).
 */
function Main({ moi, onZoom, inter }: { moi: VueJoueur; onZoom: ZoomFn; inter?: Interaction }) {
  const main = moi.main ?? [];
  return (
    <div
      className="flex min-h-[4rem] items-end justify-center overflow-x-auto px-2 pt-2"
      data-testid="main-joueur"
      aria-label={`Ta main : ${main.length} carte(s)`}
    >
      {main.length === 0 ? (
        <span className="pb-4 text-sm italic text-muted-foreground">Main vide.</span>
      ) : (
        main.map((c, i) => {
          const illumine = !!inter?.illumineRef(c.instance_id);
          return (
            <div
              key={c.instance_id}
              className="h-[4.25rem] w-[3rem] shrink-0 origin-bottom transition-transform hover:z-10 hover:-translate-y-2 hover:scale-110"
              style={{ marginLeft: i === 0 ? 0 : "-0.75rem" }}
            >
              <BoardCard
                carte={c}
                etiquette="Main"
                illumine={illumine}
                onActiver={illumine && inter ? () => inter.activerRef(c.instance_id) : undefined}
                onPeek={(peeked) => onZoom(peeked)}
              />
            </div>
          );
        })
      )}
    </div>
  );
}
