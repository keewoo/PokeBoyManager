// Bandeau d'état de la connexion temps réel (lot `j-temps-reel`).
//
// Principe du jeu : « on n'attend jamais devant un écran muet ». Quand la connexion directe est
// perdue et que la partie continue par interrogation périodique (repli), on le **dit** — et on
// rassure : la partie n'est pas interrompue, seulement ralentie. Le composant n'affiche rien quand
// tout va bien (« direct ») : il ne distrait pas du plateau.

import { cn } from "@/lib/utils";
import type { EtatConnexion } from "@/lib/game/realtime";

const MESSAGES: Record<EtatConnexion, { texte: string; ton: string } | null> = {
  // Connexion directe : rien à afficher, le jeu parle de lui-même.
  direct: null,
  connexion: {
    texte: "Connexion à la partie…",
    ton: "border-border text-muted-foreground",
  },
  degrade: {
    texte: "Connexion dégradée : la partie continue, un peu plus lentement.",
    ton: "border-[rgba(255,215,0,0.6)] text-gold-foreground shadow-[inset_0_0_16px_rgba(255,215,0,0.16)]",
  },
  ferme: {
    texte: "Partie fermée.",
    ton: "border-border text-muted-foreground",
  },
};

/** Props de {@link StatutConnexion} : l'état du canal temps réel à annoncer (rien si `direct`). */
export type StatutConnexionProps = {
  etat: EtatConnexion;
  className?: string;
};

/**
 * Affiche l'état de la connexion temps réel, ou rien quand la connexion est directe.
 *
 * `role="status"` + `aria-live="polite"` : un lecteur d'écran annonce le passage en mode dégradé
 * sans voler le focus — accessibilité du jeu (`docs/UI-UX.md`).
 */
export function StatutConnexion({ etat, className }: StatutConnexionProps) {
  const message = MESSAGES[etat];
  if (!message) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-etat={etat}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border bg-transparent px-3 py-1 font-heading text-xs font-bold tracking-[0.05em]",
        message.ton,
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "h-2 w-2 rounded-full",
          etat === "degrade" ? "animate-pulse bg-gold" : "bg-muted-foreground",
        )}
      />
      {message.texte}
    </div>
  );
}
