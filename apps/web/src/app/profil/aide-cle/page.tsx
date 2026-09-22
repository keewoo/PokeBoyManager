import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Ajouter ta clé IA",
  description:
    "Où trouver ta clé Claude, Gemini ou ChatGPT, combien ça coûte, et ce que PokéBoy en fait.",
};

// Page d'aide réservée à l'espace connecté (préfixe `/profil` gardé par `src/middleware.ts`).
// Pas de logique cliente : de simples sections en Server Component — accessibles au clavier
// sans JS, sans nonce CSP à gérer. Elle est atteignable depuis l'onglet « Mon IA » du profil
// (`ai-tab.tsx`) et depuis l'écran d'envoi de photos sans clé (`ajouter/upload-view.tsx`).
//
// Mise en page en `flex flex-col`, pas `grid` : une piste de grille implicite est dimensionnée
// en `max-content`, donc ne rétrécit pas sous 640px et provoque un défilement horizontal
// (mesuré à 320/390px par `e2e/responsive.spec.ts`). Le flex en colonne contraint les enfants
// à la largeur du conteneur.

type Provider = {
  id: string;
  name: string;
  color: string;
  letter: string;
  consoleUrl: string;
  consoleLabel: string;
  steps: React.ReactNode[];
  note?: React.ReactNode;
};

// Les libellés d'interface des consoles changent souvent : on décrit l'action et on donne un
// repère stable (nom de section, forme de la clé, besoin d'un crédit) plutôt qu'un bouton précis
// qui pourrait être renommé. Les URL sont celles déjà utilisées par l'onglet « Mon IA » et
// vérifiées avant mise en ligne (voir le compte rendu du lot).
const PROVIDERS: Provider[] = [
  {
    id: "anthropic",
    name: "Claude · Anthropic",
    color: "#C8663F",
    letter: "A",
    consoleUrl: "https://console.anthropic.com/settings/keys",
    consoleLabel: "console.anthropic.com",
    steps: [
      "Va sur console.anthropic.com et connecte-toi (ou crée un compte).",
      "Ajoute un moyen de paiement et quelques euros de crédit, dans la partie facturation (« Billing »).",
      "Ouvre les réglages, section « API keys », puis crée une clé (« Create key »).",
      <>
        Copie la clé tout de suite : elle commence par <code>sk-ant-</code> et ne s&rsquo;affiche
        qu&rsquo;une seule fois.
      </>,
      "Colle-la dans ton profil, onglet « Mon IA », sur la ligne « Claude · Anthropic ».",
    ],
  },
  {
    id: "gemini",
    name: "Gemini · Google",
    color: "#3E7BE6",
    letter: "G",
    consoleUrl: "https://aistudio.google.com/app/apikey",
    consoleLabel: "aistudio.google.com",
    steps: [
      "Va sur aistudio.google.com et connecte-toi avec un compte Google.",
      "Demande une clé API (« Get API key »).",
      "Crée la clé, puis copie-la.",
      "Colle-la dans ton profil, onglet « Mon IA », sur la ligne « Gemini · Google ».",
    ],
    note: (
      <>
        Google propose une offre gratuite limitée : tu peux souvent commencer sans carte
        bancaire.
      </>
    ),
  },
  {
    id: "openai",
    name: "ChatGPT · OpenAI",
    color: "#10A37F",
    letter: "O",
    consoleUrl: "https://platform.openai.com/api-keys",
    consoleLabel: "platform.openai.com",
    steps: [
      <>
        Va sur platform.openai.com et connecte-toi. Attention : c&rsquo;est la plateforme pour
        développeurs, différente de l&rsquo;application ChatGPT.
      </>,
      "Ajoute du crédit prépayé dans la partie facturation (« Billing ») : sans crédit, la clé ne répond pas.",
      "Ouvre « API keys » et crée une clé (« Create new secret key »).",
      <>
        Copie la clé tout de suite : elle commence par <code>sk-</code> et ne s&rsquo;affiche
        qu&rsquo;une seule fois.
      </>,
      "Colle-la dans ton profil, onglet « Mon IA », sur la ligne « ChatGPT · OpenAI ».",
    ],
  },
];

// Message exact affiché par le site pour chaque panne, pour que l'utilisateur fasse le lien.
// Source de vérité : `apps/api/src/pbm_api/ai/providers.py` (bouton « Tester ») et
// `apps/api/src/pbm_api/ai/errors.py` (pendant la reconnaissance).
const TROUBLES: { title: string; messages: string[]; fix: React.ReactNode }[] = [
  {
    title: "Clé refusée ou mauvais fournisseur",
    messages: ["Clé refusée par le fournisseur.", "Clé invalide ou révoquée par le fournisseur."],
    fix: (
      <>
        Vérifie que tu as collé la clé sur la bonne ligne : une clé Claude collée sur la ligne
        OpenAI est refusée. Si la clé a été supprimée ou régénérée chez le fournisseur, crée-en
        une nouvelle et remplace-la.
      </>
    ),
  },
  {
    title: "Quota épuisé ou crédit à zéro",
    messages: ["Quota dépassé chez le fournisseur."],
    fix: (
      <>
        Ta clé est bonne, mais ton compte chez le fournisseur n&rsquo;a plus de crédit ou a
        atteint sa limite. Ajoute du crédit, ou attends la remise à zéro du quota gratuit.
      </>
    ),
  },
  {
    title: "Fournisseur momentanément indisponible",
    messages: [
      "Fournisseur surchargé — réessayez plus tard.",
      "Fournisseur injoignable — réessayez plus tard.",
    ],
    fix: <>Ce n&rsquo;est pas ta clé : le service du fournisseur est occupé. Réessaie dans quelques minutes.</>,
  },
];

export default function AideClePage() {
  return (
    <article className="prose flex max-w-3xl flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="font-heading text-3xl font-bold text-foreground">Ajouter ta clé IA</h1>
        <p className="text-muted-foreground">
          Ta clé sert à reconnaître tes cartes sur tes photos et à générer les fiches manquantes.
          Elle ne sert jamais à autre chose.
        </p>
      </header>

      {/* 1 — Choisir un fournisseur et créer une clé */}
      <section className="flex flex-col gap-4">
        <h2 className="font-heading text-xl font-bold text-foreground">
          Choisir un fournisseur et créer une clé
        </h2>
        <p className="text-muted-foreground">
          Un seul fournisseur suffit. Prends celui pour lequel tu as déjà un compte, ou Gemini si
          tu veux commencer sans payer.
        </p>

        {PROVIDERS.map((provider) => (
          <div
            key={provider.id}
            className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4"
          >
            <div className="flex items-center gap-3">
              <span
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-base font-extrabold text-white"
                style={{ backgroundColor: provider.color }}
                aria-hidden
              >
                {provider.letter}
              </span>
              <h3 className="font-heading text-base font-bold text-foreground">{provider.name}</h3>
            </div>

            <ol className="list-decimal space-y-1.5 pl-5 text-sm text-muted-foreground">
              {provider.steps.map((step, index) => (
                <li key={index}>{step}</li>
              ))}
            </ol>

            {provider.note && <p className="text-sm text-muted-foreground">{provider.note}</p>}

            <a
              href={provider.consoleUrl}
              target="_blank"
              rel="noreferrer"
              className="break-words text-sm font-medium text-foreground underline underline-offset-2"
            >
              Ouvrir {provider.consoleLabel}
            </a>
          </div>
        ))}
      </section>

      {/* 2 — Combien ça coûte */}
      <section className="flex flex-col gap-3">
        <h2 className="font-heading text-xl font-bold text-foreground">Combien ça coûte</h2>
        <ul className="list-disc space-y-1.5 pl-5 text-muted-foreground">
          <li>Reconnaître une photo de 9 cartes coûte environ 0,05 €.</li>
          <li>
            Pour donner un ordre d&rsquo;idée : générer les 22 169 fiches de tout le catalogue
            PokéBoy a coûté 27,32 € en tout.
          </li>
          <li>
            Ce coût est facturé par ton fournisseur (Anthropic, Google ou OpenAI) sur ton propre
            compte, jamais par PokéBoy. On ne prend aucune commission et on ne voit pas ta facture.
          </li>
        </ul>
      </section>

      {/* 3 — Ce que PokéBoy fait de ta clé */}
      <section className="flex flex-col gap-3">
        <h2 className="font-heading text-xl font-bold text-foreground">
          Ce que PokéBoy fait de ta clé
        </h2>
        <ul className="list-disc space-y-1.5 pl-5 text-muted-foreground">
          <li>Elle est chiffrée en base (AES-256-GCM), avec une clé maître conservée hors de la base.</li>
          <li>
            Elle n&rsquo;est jamais réaffichée en entier : tu ne revois qu&rsquo;un masque, par
            exemple <code>sk-ant-…4f2a</code>.
          </li>
          <li>Elle n&rsquo;est jamais écrite dans un journal.</li>
          <li>Elle sert uniquement à tes propres traitements : reconnaître tes photos, générer tes fiches.</li>
          <li>Tu peux la supprimer à tout moment, en un clic, depuis l&rsquo;onglet « Mon IA ».</li>
        </ul>
        <p className="text-muted-foreground">
          Le détail est dans la{" "}
          <Link href="/confidentialite" className="font-medium text-foreground underline underline-offset-2">
            politique de confidentialité
          </Link>
          .
        </p>
      </section>

      {/* 4 — Si ça ne marche pas */}
      <section className="flex flex-col gap-3">
        <h2 className="font-heading text-xl font-bold text-foreground">Si ça ne marche pas</h2>
        <p className="text-muted-foreground">
          Quand tu testes ta clé ou que tu lances une reconnaissance, le site affiche un message
          précis. Voici ce qu&rsquo;il veut dire.
        </p>
        <div className="flex flex-col gap-3">
          {TROUBLES.map((trouble) => (
            <div key={trouble.title} className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
              <h3 className="font-heading text-base font-bold text-foreground">{trouble.title}</h3>
              <ul className="space-y-1">
                {trouble.messages.map((message) => (
                  <li key={message} className="text-sm text-foreground">
                    <span className="inline-block break-words rounded bg-secondary px-1.5 py-0.5 font-mono text-xs">
                      « {message} »
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-sm text-muted-foreground">{trouble.fix}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 5 — Sans clé */}
      <section className="flex flex-col gap-3 rounded-xl border border-dashed border-border bg-muted p-4">
        <h2 className="font-heading text-xl font-bold text-foreground">Et sans clé ?</h2>
        <p className="text-muted-foreground">
          Sans clé, tu peux quand même utiliser PokéBoy : ajoute tes cartes à la main par la
          recherche, garde ta collection, suis leurs valeurs et consulte les fiches. Seule la
          reconnaissance automatique de tes photos reste indisponible tant qu&rsquo;aucune clé
          n&rsquo;est enregistrée.
        </p>
      </section>

      {/* Libellés longs : sans `whitespace-normal`, le défaut `whitespace-nowrap` du composant
          `Button` déborde à 320px (même piège que `ajouter/upload-view.tsx`). On les laisse
          passer sur deux lignes en gardant la hauteur de pilule en desktop. */}
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <Button asChild className="h-auto min-h-11 whitespace-normal py-2 text-center leading-tight">
          <Link href="/profil?onglet=ia">Coller ma clé dans « Mon IA »</Link>
        </Button>
        <Button asChild variant="outline" className="h-auto min-h-11 whitespace-normal py-2 text-center leading-tight">
          <Link href="/ajouter">Ajouter des photos</Link>
        </Button>
      </div>
    </article>
  );
}
