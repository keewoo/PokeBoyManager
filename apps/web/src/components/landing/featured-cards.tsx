import { cardImageUrl } from "@/lib/api/validation";
import type { FeaturedCard } from "@/lib/api/featured-cards";

import { FeaturedCardImage } from "./featured-card-image";

// Purement présentationnel (les données viennent de `page.tsx`, seul point de récupération
// serveur de l'accueil) : reste un composant synchrone, testable avec `@testing-library/react`
// comme le reste de l'arbre `LandingPage` — un composant serveur asynchrone imbriqué ici ne
// pourrait pas être rendu par le réconciliateur client qu'utilisent ces tests.
export function FeaturedCards({ cards }: { cards: FeaturedCard[] }) {
  if (cards.length === 0) return null;

  return (
    <section className="mt-9" aria-labelledby="featured-cards-heading">
      <h2 id="featured-cards-heading" className="font-heading text-lg font-bold text-foreground">
        Dans le catalogue
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Image officielle, extension et numéro : ce que PokeBoy reconnaît pour chacune de tes cartes.
      </p>
      <div className="mt-3.5 grid grid-cols-3 gap-2.5 sm:grid-cols-5 lg:grid-cols-9">
        {cards.map((card) => (
          <FeaturedCardImage
            key={card.id}
            src={cardImageUrl(card.id, "low")}
            alt={`${card.name} · ${card.set_name} n°${card.number}`}
          />
        ))}
      </div>
    </section>
  );
}
