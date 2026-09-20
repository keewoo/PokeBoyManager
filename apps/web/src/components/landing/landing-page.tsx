import Link from "next/link";

import { Button } from "@/components/ui/button";
import { LegalFooter } from "@/components/legal-footer";
import type { FeaturedCard } from "@/lib/api/featured-cards";

import { FeaturedCards } from "./featured-cards";
import { HeroImage } from "./hero-image";

const STEPS = [
  {
    kicker: "1 · PHOTO",
    title: "Une carte ou tout un classeur",
    description:
      "Glisse tes photos ou prends-les au téléphone. Les cartes sont détectées et redressées une par une.",
  },
  {
    kicker: "2 · RECONNAISSANCE",
    title: "Tu vérifies, tu valides",
    description:
      "Pour chaque carte : la proposition de l'IA à côté de l'image officielle, et deux autres candidats si elle hésite.",
  },
  {
    kicker: "3 · VALEUR",
    title: "Ta collection, cotée chaque jour",
    description:
      "Prix Cardmarket et TCGplayer relevés quotidiennement, courbe par carte, hausses et baisses de la semaine.",
  },
  {
    kicker: "4 · HISTOIRE",
    title: "Chaque carte raconte quelque chose",
    description:
      "Illustrateur, anecdotes sourcées, rareté, et ce qu'elle vaut encore en tournoi.",
  },
];

const AI_PROVIDERS = ["Claude · Anthropic", "Gemini · Google", "ChatGPT · OpenAI"];

export function LandingPage({ featuredCards }: { featuredCards: FeaturedCard[] }) {
  return (
    <div>
      <div className="grid items-center gap-9 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div>
          <span className="font-mono text-xs font-semibold text-muted-foreground">
            ESPACE PRIVÉ · TON IA · TES CARTES
          </span>
          <h1 className="mt-2.5 break-words font-heading text-3xl font-extrabold leading-[1.1] text-foreground sm:text-4xl sm:leading-[1.05] lg:text-5xl">
            Photographie ton classeur.
            <br />
            <em className="text-primary not-italic">On retrouve chaque carte</em> et ce qu&apos;elle
            vaut.
          </h1>
          <p className="mt-3.5 max-w-md text-lg text-muted-foreground">
            Une photo, même de neuf cartes à la fois : l&apos;IA de ton choix identifie l&apos;extension,
            le numéro et l&apos;état, puis PokeBoy suit leur valeur jour après jour.
          </p>
          <div className="mt-5 flex flex-wrap gap-2.5">
            <Button asChild size="lg">
              <Link href="/inscription">Créer mon espace</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/connexion">J&apos;ai déjà un compte</Link>
            </Button>
          </div>
        </div>
        <HeroImage />
      </div>

      <FeaturedCards cards={featuredCards} />

      <div className="mt-9 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((step) => (
          <div key={step.kicker} className="grid gap-1.5 border-t-[3px] border-foreground bg-card p-4">
            <span className="font-mono text-xs font-semibold text-primary">{step.kicker}</span>
            <h3 className="font-heading text-lg font-bold text-foreground">{step.title}</h3>
            <p className="text-sm text-muted-foreground">{step.description}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-2 rounded-xl border border-border bg-card p-5">
        <h3 className="font-heading text-lg font-bold text-foreground">Apporte ta propre IA</h3>
        <p className="text-sm text-muted-foreground">
          Ta clé reste à toi : chiffrée, jamais affichée en entier, utilisée seulement pour tes photos.
          Tu choisis le fournisseur.
        </p>
        <div className="mt-1 flex flex-wrap gap-2.5">
          {AI_PROVIDERS.map((provider) => (
            <span
              key={provider}
              className="inline-flex items-center rounded-full border border-border bg-secondary px-2.5 py-1 font-sans text-xs font-semibold text-secondary-foreground"
            >
              {provider}
            </span>
          ))}
        </div>
      </div>

      <LegalFooter />
    </div>
  );
}
