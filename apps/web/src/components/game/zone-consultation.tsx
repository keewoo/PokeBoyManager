"use client";

import { useState } from "react";

import { BoardCard } from "@/components/game/board-card";
import { cn } from "@/lib/utils";
import type { VueCarte } from "@/lib/game/plateau";

/**
 * Consultation des zones (lot `j-plateau-layout`).
 *
 * Deux zones, deux traitements, dictés par ce que le serveur laisse voir — on ne décide de rien ici :
 *
 * - {@link ZonePublique} : une zone **publique** (défausse, zone perdue). Son contenu est visible des
 *   deux joueurs ; on peut l'ouvrir pour la parcourir.
 * - {@link ZoneCachee} : une zone **cachée** (pioche, récompenses, main adverse). Le serveur n'en
 *   donne qu'un nombre : on affiche ce **compteur**, jamais de contenu — il n'existe pas côté client.
 */

/** Un bouton-pile compact : une étiquette, un compteur, et l'aspect d'une pile de cartes. */
function PileBouton({
  titre,
  nombre,
  onClick,
  className,
  ...reste
}: {
  titre: string;
  nombre: number;
  onClick?: () => void;
  className?: string;
} & React.HTMLAttributes<HTMLElement>) {
  const classes = cn(
    "flex aspect-[63/88] w-[4.6875em] flex-col items-center justify-center gap-[0.15em] rounded-[0.4em] border text-center",
    onClick
      ? "cursor-pointer border-[rgba(255,215,0,0.5)] bg-[rgba(255,215,0,0.08)] hover:bg-[rgba(255,215,0,0.16)]"
      : "border-[rgba(255,255,255,0.3)] bg-[rgba(255,255,255,0.06)]",
    className,
  );
  const contenu = (
    <>
      <span className="font-mono text-[1em] font-bold text-foreground">{nombre}</span>
      <span className="text-[0.55em] uppercase tracking-[0.08em] text-muted-foreground">{titre}</span>
    </>
  );
  // Une zone consultable est un vrai bouton ; une zone cachée n'est qu'un affichage (aucune action).
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={classes} {...reste}>
        {contenu}
      </button>
    );
  }
  return (
    <div className={classes} {...reste}>
      {contenu}
    </div>
  );
}

/**
 * Une zone publique consultable. Fermée, c'est une pile avec son compteur ; ouverte, un panneau qui
 * liste les cartes. Vide, elle le dit (jamais un panneau muet). L'ouverture est locale à ce
 * composant : consulter sa défausse ne touche pas l'état de la partie.
 */
export function ZonePublique({
  titre,
  cartes,
  className,
}: {
  titre: string;
  cartes: VueCarte[];
  className?: string;
}) {
  const [ouvert, setOuvert] = useState(false);
  return (
    <>
      <PileBouton
        titre={titre}
        nombre={cartes.length}
        onClick={() => setOuvert(true)}
        className={className}
        aria-label={`${titre} : ${cartes.length} carte(s) — ouvrir pour consulter`}
        data-testid={`zone-publique-${titre}`}
      />
      {ouvert && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(5,10,48,0.8)] p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={`${titre} — ${cartes.length} carte(s)`}
          data-testid={`zone-contenu-${titre}`}
          onClick={() => setOuvert(false)}
        >
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-2xl border border-border bg-card p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-heading text-lg font-bold capitalize text-gold">{titre}</h2>
              <button
                type="button"
                onClick={() => setOuvert(false)}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
              >
                Fermer
              </button>
            </div>
            {cartes.length === 0 ? (
              <p className="text-sm italic text-muted-foreground">Zone vide.</p>
            ) : (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] gap-3">
                {cartes.map((c) => (
                  <div key={c.instance_id} className="w-full">
                    <BoardCard carte={c} etiquette={titre} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

/**
 * Une zone cachée : rien d'autre que son compteur. Le serveur ne donne qu'un nombre (anti-triche) ;
 * l'écran ne promet donc aucun contenu à ouvrir.
 */
export function ZoneCachee({
  titre,
  nombre,
  className,
}: {
  titre: string;
  nombre: number;
  className?: string;
}) {
  return (
    <PileBouton
      titre={titre}
      nombre={nombre}
      className={className}
      aria-label={`${titre} : ${nombre} carte(s), face cachée`}
      data-testid={`zone-cachee-${titre}`}
    />
  );
}
