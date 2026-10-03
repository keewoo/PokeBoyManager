import { CardDetailView } from "./card-detail-view";

/** Route `/carte/[id]` (maquette `docs/UI-UX.md` § « Fiche carte »). Point d'entrée serveur
 * minimal : récupère l'identifiant de carte depuis l'URL et délègue tout l'affichage (en-tête,
 * onglets, appels API) à `CardDetailView`, côté client. */
export default async function FicheCartePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return <CardDetailView cardId={id} />;
}
