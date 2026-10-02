"use client";

import { BoardCard } from "@/components/game/board-card";
import type { VueCarte, VuePokemon } from "@/lib/game/plateau";

/**
 * Agrandissement d'une carte **sans quitter la partie** (lot `j-plateau-layout`, critère « le texte
 * d'une carte zoomée est lisible sans pincer l'écran »).
 *
 * C'est une surcouche non modale : elle s'ouvre au survol, au focus ou au maintien long d'une carte
 * du plateau (`BoardCard onPeek`), et se ferme quand ce survol cesse — ou, au doigt, en touchant le
 * fond. Elle ne bloque pas le jeu derrière : le plateau reste visible et autoritaire.
 */
export function CardZoom({
  carte,
  pokemon,
  onClose,
}: {
  carte: VueCarte | null;
  pokemon?: VuePokemon;
  onClose: () => void;
}) {
  if (!carte) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(5,10,48,0.72)] p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="false"
      aria-label={`Carte agrandie : ${carte.ref}`}
      data-testid="card-zoom"
      onClick={onClose}
    >
      {/* Le zoom lui-même ne propose pas de nouveau zoom (`onPeek` absent) : on ne s'emboîte pas. */}
      <BoardCard carte={carte} pokemon={pokemon} taille="zoom" />
    </div>
  );
}
