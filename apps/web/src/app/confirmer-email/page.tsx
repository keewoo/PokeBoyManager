import { Suspense } from "react";

import { ConfirmerEmailStatus } from "./confirmer-email-status";

/**
 * Enveloppe de la route `/confirmer-email`. Isole `ConfirmerEmailStatus` dans un `Suspense`
 * car ce composant client lit les paramètres d'URL (`useSearchParams`), ce qu'App Router
 * exige d'encadrer.
 */
export default function ConfirmerEmailPage() {
  return (
    <Suspense>
      <ConfirmerEmailStatus />
    </Suspense>
  );
}
