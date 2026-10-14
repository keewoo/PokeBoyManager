"use client";

import { BoardCard } from "@/components/game/board-card";
import type { VueCarte, VuePokemon } from "@/lib/game/plateau";
import { useModale } from "@/lib/game/use-modale";

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
  // Le contenu est un composant à part pour que son clavier (`useModale`) ne soit monté que quand la
  // surcouche existe : un crochet ne peut pas vivre après un `return null` conditionnel.
  if (!carte) return null;
  return <ZoomOuvert carte={carte} pokemon={pokemon} onClose={onClose} />;
}

/**
 * La surcouche réellement ouverte. **Échap la ferme** (lot `j-accessibilite-jeu`) : c'est la touche
 * que tout le monde essaie, et au clavier il n'y avait aucune autre sortie — le zoom s'ouvre au
 * focus d'une carte, donc en tabulant. Le Tab n'est **pas** piégé ici : la surcouche est non modale
 * (le plateau reste autoritaire derrière), en sortir au clavier est le comportement attendu.
 */
function ZoomOuvert({
  carte,
  pokemon,
  onClose,
}: {
  carte: VueCarte;
  pokemon?: VuePokemon;
  onClose: () => void;
}) {
  const ref = useModale({ onFermer: onClose, piege: false });
  return (
    <div
      ref={ref}
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(5,10,48,0.72)] p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="false"
      aria-label={`Carte agrandie : ${carte.ref}. Échap pour fermer.`}
      data-testid="card-zoom"
      onClick={onClose}
    >
      {/* Le zoom lui-même ne propose pas de nouveau zoom (`onPeek` absent) : on ne s'emboîte pas. */}
      <BoardCard carte={carte} pokemon={pokemon} taille="zoom" />
    </div>
  );
}
