"use client";

import { CardImage } from "@/components/card-image";

// Conservé comme point d'entrée nommé de l'accueil visiteur ; tout le comportement vit
// désormais dans `CardImage`, seul endroit qui traite une carte sans image officielle.
export function FeaturedCardImage({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="aspect-[63/88] w-full overflow-hidden rounded-md border border-border bg-muted">
      <CardImage src={src} alt={alt} className="h-full w-full object-cover" label="Image à venir" />
    </div>
  );
}
