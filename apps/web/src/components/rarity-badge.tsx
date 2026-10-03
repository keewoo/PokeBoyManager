import { Badge } from "@/components/ui/badge";

/** Les six paliers de rareté d'une carte, de la commune à la secrète. */
export type RarityTier =
  | "commune"
  | "peu-commune"
  | "rare"
  | "rare-holo"
  | "ultra-rare"
  | "secrete";

/** Props de `RarityBadge` : le palier de rareté à représenter. */
export type RarityBadgeProps = {
  rarity: RarityTier;
  className?: string;
};

const RARITY_LABELS: Record<RarityTier, string> = {
  commune: "Commune",
  "peu-commune": "Peu commune",
  rare: "Rare",
  "rare-holo": "Rare holo",
  "ultra-rare": "Ultra rare",
  secrete: "Secrète",
};

const GOLD_TIERS: readonly RarityTier[] = ["rare-holo", "ultra-rare", "secrete"];

/**
 * Badge de rareté d'une carte : libellé français via le `Badge` de base. Les paliers élevés
 * (rare holo, ultra rare, secrète) prennent la variante dorée, les autres le simple contour —
 * la distinction se lit au texte comme à la couleur.
 */
export function RarityBadge({ rarity, className }: RarityBadgeProps) {
  const isGold = GOLD_TIERS.includes(rarity);
  return (
    <Badge data-slot="rarity-badge" variant={isGold ? "gold" : "outline"} className={className}>
      {RARITY_LABELS[rarity]}
    </Badge>
  );
}
