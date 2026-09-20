import { CardDetailView } from "./card-detail-view";

export default async function FicheCartePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return <CardDetailView cardId={id} />;
}
