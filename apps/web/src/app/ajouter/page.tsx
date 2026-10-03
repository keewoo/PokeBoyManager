import { UploadView } from "./upload-view";

/** Écran `/ajouter` (étape 1 « Photos » du parcours en 3 temps, maquette `docs/UI-UX.md`
 * § « Les écrans »). Point d'entrée serveur minimal : toute la logique (envoi, estimation du
 * coût, reprise des lots à valider, import CSV) vit dans `UploadView`, côté client. */
export default function AjouterPage() {
  return <UploadView />;
}
