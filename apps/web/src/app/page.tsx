import { EmptyState } from "@/components/empty-state";

export default function Home() {
  return (
    <EmptyState
      title="PokeBoyManager"
      description="La page d'accueil publique arrive avec le lot v1-accueil. En attendant, connecte-toi ou crée un compte pour préparer ta collection."
      action={{ label: "Créer un compte", href: "/inscription" }}
    />
  );
}
