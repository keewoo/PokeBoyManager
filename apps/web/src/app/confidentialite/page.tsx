import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Politique de confidentialité — PokéBoy",
  description: "Quelles données PokéBoy conserve, pourquoi, et comment les supprimer.",
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

      <h2 className="font-heading text-xl font-bold text-foreground">Sous-traitants IA</h2>
      <p className="text-muted-foreground">
        Reconnaître une carte et estimer son état demande un appel à l&apos;IA que tu as toi-même
        choisie et dont tu fournis la clé, dans l&apos;onglet « Mon IA » de ton profil : Anthropic
        (Claude), Google (Gemini) ou OpenAI (ChatGPT). Seule la photo envoyée à cet appel-là quitte
        PokéBoy, vers le seul fournisseur que tu as sélectionné ; aucune photo ni clé n&apos;est
        transmise à un autre sous-traitant. Sans clé enregistrée, aucun appel IA n&apos;est fait — la
        reconnaissance reste désactivée, l&apos;ajout manuel à ta collection reste possible.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Espace privé</h2>
      <p className="text-muted-foreground">
        Ta collection n&apos;est visible que par toi, une fois connecté à ton compte.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Durée de conservation</h2>
      <ul className="text-muted-foreground">
        <li>Compte (e-mail, mot de passe) et collection : tant que ton compte existe.</li>
        <li>Photos de cartes et avatar : jusqu&apos;à ce que tu les supprimes ou que tu fermes ton compte.</li>
        <li>
          Clés IA : jusqu&apos;à ce que tu les retires de l&apos;onglet « Mon IA », ou à la fermeture du
          compte — jamais journalisées ni conservées ailleurs.
        </li>
        <li>Sessions de connexion : 30 jours d&apos;inactivité, ou immédiatement si tu te déconnectes.</li>
        <li>
          Archive d&apos;export : 24 heures après sa préparation, le temps de la télécharger — passé ce
          délai, le lien ne fonctionne plus et le fichier est effacé.
        </li>
      </ul>
      <p className="text-muted-foreground">
        La suppression de ton compte (menu « Mon profil » → « Mes données » → « Supprimer mon compte »)
        efface immédiatement et définitivement ta collection, tes photos, tes clés IA et tes sessions.
        Elle ne peut pas être annulée.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Exporter tes données</h2>
      <p className="text-muted-foreground">
        Depuis « Mon profil » → « Mes données » → « Préparer l&apos;export », tu reçois par e-mail un
        lien de téléchargement (valable 24 heures) vers un fichier ZIP contenant ta collection (JSON et
        CSV) et les photos que tu as prises de tes cartes.
      </p>

      <h2 className="font-heading text-xl font-bold text-foreground">Tes droits</h2>
      <p className="text-muted-foreground">
        Accès, rectification, export, suppression : depuis ton profil, ou en écrivant à
        [adresse e-mail à compléter].
      </p>
    </article>
  );
}
