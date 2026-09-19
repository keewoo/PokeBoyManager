import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Mentions légales — PokeBoyManager",
  description: "Éditeur, hébergement et contact de PokeBoyManager.",
};

export default function MentionsLegalesPage() {
  return (
    <article className="prose grid max-w-3xl gap-4">
      <p className="rounded-md border border-dashed border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
        Brouillon — à relire par JF avant mise en ligne.
      </p>
      <h1 className="font-heading text-3xl font-bold text-foreground">Mentions légales</h1>

      <h2 className="font-heading text-xl font-bold text-foreground">Éditeur du site</h2>
      <p className="text-muted-foreground">
        PokeBoyManager est édité à titre non professionnel par [nom/raison sociale à compléter],
        [adresse à compléter]. Contact : [adresse e-mail à compléter].
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Hébergement</h2>
      <p className="text-muted-foreground">
        Le site est hébergé par [hébergeur à compléter], [adresse de l&apos;hébergeur à compléter].
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Propriété intellectuelle</h2>
      <p className="text-muted-foreground">
        Les noms, images et logos Pokémon appartiennent à Nintendo, Creatures et GAME FREAK.
        PokeBoyManager n&apos;est ni édité, ni approuvé, ni affilié à ces sociétés ni à The Pokémon
        Company. Les images officielles de cartes affichées dans l&apos;application proviennent de
        catalogues tiers cités dans leurs conditions d&apos;utilisation respectives et ne sont
        utilisées qu&apos;à titre informatif, jamais comme argument commercial.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Contenu déposé par les utilisateurs</h2>
      <p className="text-muted-foreground">
        Les photos de cartes envoyées par un utilisateur restent sa propriété et ne sont utilisées que
        pour lui fournir le service (reconnaissance, gestion de sa collection).
      </p>
    </article>
  );
}
