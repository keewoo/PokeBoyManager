import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Politique de confidentialité — PokeBoyManager",
  description: "Quelles données PokeBoyManager conserve, pourquoi, et comment les supprimer.",
};

export default function ConfidentialitePage() {
  return (
    <article className="prose grid max-w-3xl gap-4">
      <p className="rounded-md border border-dashed border-border bg-muted px-3 py-2 text-sm text-muted-foreground">
        Brouillon — à relire par JF avant mise en ligne.
      </p>
      <h1 className="font-heading text-3xl font-bold text-foreground">Politique de confidentialité</h1>

      <h2 className="font-heading text-xl font-bold text-foreground">Données collectées</h2>
      <p className="text-muted-foreground">
        Compte : e-mail, mot de passe (haché, jamais en clair). Collection : photos de cartes, résultats
        de reconnaissance, exemplaires ajoutés. Clés IA : chiffrées (AES-256-GCM), jamais renvoyées en
        clair ni journalisées ; seul un masque (par exemple <code>sk-ant-…4f2a</code>) est affiché.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Pourquoi ces données</h2>
      <p className="text-muted-foreground">
        Les photos et les clés IA ne servent qu&apos;à reconnaître tes cartes avec le fournisseur que tu
        as choisi. Aucune donnée n&apos;est vendue ni partagée à des fins publicitaires.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Espace privé</h2>
      <p className="text-muted-foreground">
        Ta collection n&apos;est visible que par toi, une fois connecté à ton compte.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Durée de conservation</h2>
      <p className="text-muted-foreground">
        Tes photos sont conservées jusqu&apos;à ce que tu les supprimes. La suppression de ton compte
        entraîne la suppression de tes photos, de ta collection et de tes clés IA.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Tes droits</h2>
      <p className="text-muted-foreground">
        Accès, rectification, suppression : depuis ton profil, ou en écrivant à
        [adresse e-mail à compléter].
      </p>
    </article>
  );
}
