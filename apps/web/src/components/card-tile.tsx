import Link from "next/link";

import { ConditionBadge, type ConditionGrade } from "@/components/condition-badge";
import { RarityBadge, type RarityTier } from "@/components/rarity-badge";
import { ValueDelta } from "@/components/value-delta";
import { cn } from "@/lib/utils";

export type CardTileProps = {
  href: string;
  name: string;
  setName: string;
  number: string;
  price: string;
  delta?: number;
  rarity: RarityTier;
  condition: ConditionGrade;
  imageUrl?: string;
  className?: string;
};

// Charte PokéBoy : la vignette est une CARTE, pas une image dans un cadre. Liseré or de
// 3 px, reflet holographique en diagonale, légère inclinaison au repos — et au survol elle
// se redresse, monte et son liseré s'allume. C'est l'état qui explique l'interaction sans
// qu'on ait à l'écrire.
export function CardTile({
  href,
  name,
  setName,
  number,
  price,
  delta,
  rarity,
  condition,
  imageUrl,
  className,
}: CardTileProps) {
  return (
    <Link
      href={href}
      data-slot="card-tile"
      className={cn(
        "group flex flex-col gap-3 rounded-lg p-3 text-left transition-transform",
        "pbm-surface -rotate-[1.2deg] hover:rotate-0 hover:-translate-y-2.5",
        className
      )}
    >
      <div
        className={cn(
          "pbm-carte pbm-holo relative aspect-[63/88] w-full overflow-hidden rounded-md bg-muted",
          "transition-shadow group-hover:shadow-[0_0_34px_rgba(255,215,0,0.4),inset_0_0_26px_rgba(0,0,0,0.35)]"
        )}
      >
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imageUrl} alt={name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center px-2 text-center text-xs text-muted-foreground">
            Image à venir
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <RarityBadge rarity={rarity} />
        <ConditionBadge condition={condition} />
      </div>
      <div>
        <p className="truncate font-heading text-base font-bold text-foreground">{name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {setName} · {number}
        </p>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="font-heading text-lg font-extrabold text-gold">{price}</span>
        {typeof delta === "number" && <ValueDelta value={delta} />}
      </div>
    </Link>
  );
}
