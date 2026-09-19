import { Suspense } from "react";

import { ConnexionForm } from "./connexion-form";

export default function ConnexionPage() {
  return (
    <Suspense>
      <ConnexionForm />
    </Suspense>
  );
}
