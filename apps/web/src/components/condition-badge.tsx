import { Badge, type badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";

/** Les six états possibles d'une carte, du neuf (`mint`) à l'abîmé. */
export type ConditionGrade =
  | "mint"
  | "near-mint"
  | "excellent"
  | "bon"
  | "joue"
  | "abime";

/** Props de `ConditionBadge` : l'état à représenter. */
export type ConditionBadgeProps = {
  condition: ConditionGrade;
  className?: string;
};

const CONDITION_LABELS: Record<ConditionGrade, string> = {
  mint: "Mint",
  "near-mint": "Near Mint",
  excellent: "Excellent",
  bon: "Bon état",
  joue: "Jouée",
  abime: "Abîmée",
};

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

const CONDITION_VARIANT: Record<ConditionGrade, BadgeVariant> = {
  mint: "success",
  "near-mint": "success",
  excellent: "default",
  bon: "default",
  joue: "danger",
  abime: "danger",
};

/**
 * Badge d'état d'une carte : traduit le `condition` en libellé français et en couleur
 * (vert pour les bons états, violet au milieu, rose pour les mauvais) via le `Badge` de base.
 * La couleur n'est qu'un renfort du libellé, jamais la seule information.
 */
export function ConditionBadge({ condition, className }: ConditionBadgeProps) {
  return (
    <Badge data-slot="condition-badge" variant={CONDITION_VARIANT[condition]} className={className}>
      {CONDITION_LABELS[condition]}
    </Badge>
  );
}
