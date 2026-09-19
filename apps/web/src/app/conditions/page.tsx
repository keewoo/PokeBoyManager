import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Conditions générales d'utilisation — PokeBoyManager",
  description: "Ce que couvre le service PokeBoyManager et les règles d'usage de l'espace privé.",
};

export default function ConditionsPage() {
  return (
    <article className="prose grid max-w-3xl gap-4">
      <p className="rounded-md border border-dashed border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
        Brouillon — à relire par JF avant mise en ligne.
      </p>
      <h1 className="font-heading text-3xl font-bold text-foreground">
        Conditions générales d&apos;utilisation
      </h1>

      <h2 className="font-heading text-xl font-bold text-foreground">Objet</h2>
      <p className="text-muted-foreground">
        PokeBoyManager est un service privé de gestion de collection de cartes Pokémon : photo,
        reconnaissance assistée par IA, suivi de valeur.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Ton IA, ta responsabilité</h2>
      <p className="text-muted-foreground">
        La reconnaissance utilise la clé du fournisseur IA (Claude, Gemini ou OpenAI) que tu déposes
        dans ton profil. Son usage relève des conditions de ce fournisseur ; les coûts d&apos;appel sont
        les tiens.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Estimations de valeur</h2>
      <p className="text-muted-foreground">
        Les prix affichés sont des estimations construites à partir de relevés publics (Cardmarket,
        TCGplayer) ; ils n&apos;engagent pas PokeBoyManager et ne constituent pas un conseil d&apos;achat
        ou de vente.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Compte et résiliation</h2>
      <p className="text-muted-foreground">
        Tu peux supprimer ton compte à tout moment depuis ton profil ; cela supprime ta collection, tes
        photos et tes clés IA.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Non-affiliation</h2>
      <p className="text-muted-foreground">
        PokeBoyManager n&apos;est pas affilié à Nintendo, Creatures, GAME FREAK ni à The Pokémon Company.
      </p>
    </article>
  );
}
