import { Suspense } from "react";

import { ConnexionForm } from "./connexion-form";

/**
 * Enveloppe de la route `/connexion`. Monte `ConnexionForm` sous `Suspense` car il lit le
 * paramètre `next` de l'URL (`useSearchParams`), que l'App Router impose d'encadrer.
 */
export default function ConnexionPage() {
  return (
    <Suspense>
      <ConnexionForm />
    </Suspense>
  );
}
