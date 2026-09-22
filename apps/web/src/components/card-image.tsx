"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

export type CardImageProps = {
  /** URL de l'image. `undefined` ou `null` = on sait déjà qu'il n'y en a pas. */
  src?: string | null;
  alt: string;
  /** Classes de l'image ET du repli : les deux occupent exactement la même place. */
  className?: string;
  /** Texte du repli. Court dans une vignette, plus explicite sur une fiche. */
  label?: string;
  loading?: "lazy" | "eager";
};

// Une carte du catalogue n'a pas toujours d'image officielle : depuis le repli fr → en de
// l'import, 1 660 cartes existent en base sans visuel dans la locale française, et le proxy
// répond alors un 404 honnête. Sans repli, le navigateur affiche son icône d'image cassée
// avec le texte alternatif en travers de la vignette — constaté en production le 22/09.
//
// Ce composant est le SEUL endroit qui traite ce cas. Il y avait cinq traitements différents
// avant lui : un test `has_image`, deux `onError` (dont un qui se contentait de masquer
// l'image), et trois endroits sans rien du tout. Cinq traitements, c'est quatre occasions
// d'en oublier un.
export function CardImage({ src, alt, className, label = "Aucune image disponible", loading = "lazy" }: CardImageProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
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
      onError={() => setFailed(true)}
    />
  );
}
