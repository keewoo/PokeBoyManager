import { Suspense } from "react";

import { CollectionView } from "./collection-view";

/**
 * Route `/collection`. Simple coquille serveur : enveloppe `CollectionView` (client) dans un
 * `Suspense` car celle-ci lit les filtres via `useSearchParams`, qui exige une frontière Suspense
 * sous l'App Router. Toute la logique d'affichage et de chargement est dans `CollectionView`.
 */
export default function CollectionPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Chargement…</p>}>
      <CollectionView />
    </Suspense>
  );
}
