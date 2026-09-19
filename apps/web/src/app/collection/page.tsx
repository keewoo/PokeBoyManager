import { EmptyState } from "@/components/empty-state";

export default function CollectionPage() {
  return (
    <EmptyState
      title="Ta collection est vide"
      description="La grille filtrable des cartes arrive avec le lot v4-collection."
      action={{ label: "Ajouter une carte", href: "/ajouter" }}
    />
  );
}
