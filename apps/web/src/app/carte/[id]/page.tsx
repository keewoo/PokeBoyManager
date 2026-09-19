import { EmptyState } from "@/components/empty-state";

export default async function FicheCartePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <EmptyState
      title="Fiche carte"
      description={`La fiche détaillée de la carte « ${id} » (image officielle, état estimé, anecdotes, étude en jeu) arrive avec le lot v4-fiche.`}
    />
  );
}
