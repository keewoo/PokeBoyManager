import { ValidationView } from "./validation-view";

/** Écran `/ajouter/validation` (étape 3 « Validation », maquette `docs/UI-UX.md` § « Écran de
 * validation »). Lit la liste d'envois à valider dans `?uploads=<id1>,<id2>,…` (un lancer de
 * reconnaissance peut regrouper plusieurs photos) et passe les identifiants à `ValidationView`,
 * qui charge et fusionne les détections. */
export default async function ValidationPage({
  searchParams,
}: {
  searchParams: Promise<{ uploads?: string }>;
}) {
  const { uploads } = await searchParams;
  const uploadIds = (uploads ?? "").split(",").filter(Boolean);

  return <ValidationView uploadIds={uploadIds} />;
}
