"use client";

import { useState } from "react";

// Repli sur erreur : même forme que `card-tile.tsx` (grille de collection) — une carte du
// catalogue dont l'image officielle n'a pas pu être mise en cache ne doit jamais laisser un
// cadre cassé sur l'accueil visiteur.
export function FeaturedCardImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false);

  return (
    <div className="aspect-[63/88] w-full overflow-hidden rounded-md border border-border bg-muted">
      {failed ? (
        <div className="flex h-full w-full items-center justify-center px-1 text-center text-[10px] text-muted-foreground">
          Image à venir
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- image servie par le proxy de l'API, pas un asset local
        <img
          src={src}
          alt={alt}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      )}
    </div>
  );
}
