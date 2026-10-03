import { Suspense } from "react";

import { VerifierStatus } from "./verifier-status";

/**
 * Enveloppe de la route `/verifier` (vérification d'adresse e-mail à l'inscription). Monte
 * `VerifierStatus` sous `Suspense` car il lit le `token` de l'URL (`useSearchParams`).
 */
export default function VerifierPage() {
  return (
    <Suspense>
      <VerifierStatus />
    </Suspense>
  );
}
