import { Badge } from "@/components/ui/badge";

export type RarityTier =
  | "commune"
  | "peu-commune"
  | "rare"
  | "rare-holo"
  | "ultra-rare"
  | "secrete";

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

export function RarityBadge({ rarity, className }: RarityBadgeProps) {
  const isGold = GOLD_TIERS.includes(rarity);
  return (
    <Badge data-slot="rarity-badge" variant={isGold ? "gold" : "outline"} className={className}>
      {RARITY_LABELS[rarity]}
    </Badge>
  );
}
