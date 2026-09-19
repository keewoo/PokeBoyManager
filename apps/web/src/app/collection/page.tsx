import { Suspense } from "react";

import { CollectionView } from "./collection-view";

export default function CollectionPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Chargement…</p>}>
      <CollectionView />
    </Suspense>
  );
}
