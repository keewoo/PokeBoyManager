import { cn } from "@/lib/utils";
import { couleurType, ELEMENT_LABELS, codeFond, fondPour } from "@/lib/replacement-card";

export type ReplacementCardProps = {
  /** Identifiant catalogue : fige le choix du fond, la même carte garde toujours le même visuel. */
  cardId: string;
  name: string;
  /** Type élémentaire normalisé (code du jeu) ou `null` — teinte le cadre et choisit le fond. */
  elementType?: string | null;
  hp?: number | null;
  /** Catégorie (`supertype`) : "Pokémon", "Dresseur", "Énergie"… Affichée pour les non-Pokémon. */
  supertype?: string | null;
  setName?: string | null;
  cardNumber?: string | null;
  rarity?: string | null;
  /** Mêmes classes que porterait l'image officielle : la carte composée occupe exactement sa place. */
  className?: string;
  loading?: "lazy" | "eager";
};

// La carte est COMPOSÉE à partir des vraies données du catalogue (nom, PV, type, extension,
// numéro, rareté ; pour un Dresseur/une Énergie, sa catégorie). Seule la zone d'illustration
// reçoit un fond générique, déterministe d'après l'identifiant. Une mention « visuel non
// disponible » reste toujours affichée : un remplacement ne se fait jamais passer pour l'image
// officielle. Référence visuelle : `docs/visuels-remplacement/README.md`.
export function ReplacementCard({
  cardId,
  name,
  elementType,
  hp,
  supertype,
  setName,
  cardNumber,
  rarity,
  className,
  loading = "lazy",
}: ReplacementCardProps) {
  const teinte = couleurType(elementType);
  const fond = fondPour(cardId, elementType);
  // Coin haut-droit : les PV d'un Pokémon, sinon la catégorie (Dresseur, Énergie…).
  const coinHaut = hp != null ? `${hp} PV` : (supertype ?? null);
  const typeLabel = elementType ? ELEMENT_LABELS[codeFond(elementType)] : null;

  return (
    <div
      role="img"
      aria-label={`${name} — visuel non disponible`}
      className={cn(
        // `@container` : tout le texte se mesure en `cqw` (part de la largeur de la carte) pour
        // rester lisible aussi bien dans une vignette que sur la fiche en grand format.
        "@container relative flex flex-col overflow-hidden bg-[#0A1048] text-foreground",
        // Cadre doré, comme la référence validée par JF.
        "border-[0.4cqw] border-[color:var(--gold)] ring-[0.2cqw] ring-[color:var(--gold)]/40",
        className
      )}
      style={{ ["--teinte" as string]: teinte }}
    >
      {/* Bandeau : nom à gauche, PV (ou catégorie) à droite. Teinte du type sous un voile sombre. */}
      <div className="relative flex items-center justify-between gap-[2cqw] px-[4cqw] py-[2.5cqw]">
        <div className="absolute inset-0 bg-[var(--teinte)] opacity-90" aria-hidden />
        <div className="absolute inset-0 bg-black/35" aria-hidden />
        <span className="relative min-w-0 truncate font-heading text-[7cqw] font-bold leading-tight text-white drop-shadow">
          {name}
        </span>
        {coinHaut && (
          <span className="relative shrink-0 font-heading text-[6cqw] font-bold leading-tight text-[color:var(--gold)] drop-shadow">
            {coinHaut}
          </span>
        )}
      </div>

      {/* Illustration : fond générique en plein cadre + mention en bas, sur un voile. */}
      <div className="relative flex-1 overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element -- asset local servi depuis /public */}
        <img
          src={fond}
          alt=""
          aria-hidden
          loading={loading}
          className="absolute inset-0 h-full w-full object-cover"
        />
        {typeLabel && (
          <span className="absolute right-[3cqw] top-[3cqw] rounded-full bg-black/55 px-[3cqw] py-[1cqw] text-[4.5cqw] font-semibold text-white backdrop-blur-sm">
            {typeLabel}
          </span>
        )}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-[4cqw] pb-[2.5cqw] pt-[8cqw] text-center">
          <span className="text-[4.5cqw] font-semibold uppercase tracking-wide text-white/90">
            Visuel non disponible
          </span>
        </div>
      </div>

      {/* Pied : extension et numéro à gauche, rareté à droite. */}
      <div className="flex items-center justify-between gap-[2cqw] border-t-[0.3cqw] border-[color:var(--gold)]/50 bg-[#050A30] px-[4cqw] py-[2.5cqw]">
        <span className="min-w-0 truncate text-[4.5cqw] text-muted-foreground">
          {[setName, cardNumber].filter(Boolean).join(" · ") || " "}
        </span>
        {rarity && (
          <span className="shrink-0 truncate text-[4.5cqw] font-semibold text-[color:var(--violet-clair)]">
            {rarity}
          </span>
        )}
      </div>
    </div>
  );
}
