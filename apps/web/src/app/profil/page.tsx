import { Suspense } from "react";

import { ProfileTabs } from "@/components/profile/profile-tabs";

/**
 * Route `/profil`. Coquille serveur qui enveloppe `ProfileTabs` (client) dans un `Suspense`, ce
 * dernier lisant l'onglet actif via les paramètres d'URL. Toute la logique — compte, mot de passe,
 * aide à la clé IA — vit dans `ProfileTabs` et ses onglets.
 */
export default function ProfilPage() {
  return (
    <Suspense>
      <ProfileTabs />
    </Suspense>
  );
}
