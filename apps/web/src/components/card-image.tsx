"use client";

import { useState } from "react";

import { ReplacementCard, type ReplacementCardProps } from "@/components/replacement-card";
import { cn } from "@/lib/utils";

/** Données d'une carte, pour composer un visuel de remplacement à défaut d'image officielle. */
export type CardImageReplacement = Omit<ReplacementCardProps, "className" | "loading">;

export type CardImageProps = {
  /** URL de l'image. `undefined` ou `null` = on sait déjà qu'il n'y en a pas. */
  src?: string | null;
  alt: string;
  /** Classes de l'image ET du repli : les deux occupent exactement la même place. */
  className?: string;
  /** Texte du repli simple. Ignoré si `replacement` est fourni (on compose alors la carte). */
  label?: string;
  loading?: "lazy" | "eager";
  /**
   * Données de la carte. Quand elles sont là, une carte sans image officielle est COMPOSÉE
   * (nom, PV, type, extension, numéro, rareté) plutôt que remplacée par un simple cadre.
   */
  replacement?: CardImageReplacement;
};

// Une carte du catalogue n'a pas toujours d'image officielle : 3 827 cartes existent en base sans
// visuel (vieilles extensions et promos), et le proxy répond alors un 404 honnête. Sans repli, le
// navigateur affiche son icône d'image cassée avec le texte alternatif en travers de la vignette.
//
// Ce composant est le SEUL endroit qui traite ce cas. Deux niveaux de repli :
//   - avec `replacement`, une carte est COMPOSÉE (`ReplacementCard`) — le cas nominal du catalogue ;
//   - sans, un cadre sobre avec un `label` (photo personnelle absente, accueil visiteur).
export function CardImage({
  src,
  alt,
  className,
  label = "Aucune image disponible",
  loading = "lazy",
  replacement,
}: CardImageProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    if (replacement) {
      return <ReplacementCard {...replacement} className={className} loading={loading} />;
    }
    return (
      <div
        role="img"
        aria-label={`${alt} — ${label}`}
        className={cn(
          "flex items-center justify-center border border-dashed border-[rgba(157,0,255,0.5)] bg-[rgba(6,11,50,0.6)] px-2 text-center text-xs text-muted-foreground",
          className
        )}
      >
        {label}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element -- image servie par le proxy de l'API, pas un asset local
    <img
      src={src}
      alt={alt}
      loading={loading}
      className={className}
      onError={() => {
        // Le proxy avait une URL et a échoué : ce n'est PAS le cas connu « pas d'image » (src
        // valait alors `null`). On bascule sur le repli SANS masquer l'incident — un fond de
        // remplacement là où une image officielle existe est une panne du proxy, pas un cas normal.
        console.warn(`Image officielle injoignable, repli affiché : ${src}`);
        setFailed(true);
      }}
    />
  );
}
