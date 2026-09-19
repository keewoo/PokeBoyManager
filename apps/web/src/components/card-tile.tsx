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
      className={cn("group flex flex-col gap-2 text-left", className)}
    >
      <div className="relative aspect-[63/88] w-full overflow-hidden rounded-lg border border-border bg-muted transition-transform group-hover:-translate-y-1">
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
        <p className="truncate text-sm font-semibold text-foreground">{name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {setName} · {number}
        </p>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm font-semibold text-foreground">{price}</span>
        {typeof delta === "number" && <ValueDelta value={delta} />}
      </div>
    </Link>
  );
}
