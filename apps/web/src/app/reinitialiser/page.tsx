import { Suspense } from "react";

import { ReinitialiserForm } from "./reinitialiser-form";

/**
 * Enveloppe de la route `/reinitialiser` (choix d'un nouveau mot de passe depuis un lien reçu
 * par e-mail). Monte `ReinitialiserForm` sous `Suspense` car il lit le `token` de l'URL
 * (`useSearchParams`).
 */
export default function ReinitialiserPage() {
  return (
    <Suspense>
      <ReinitialiserForm />
    </Suspense>
  );
}
