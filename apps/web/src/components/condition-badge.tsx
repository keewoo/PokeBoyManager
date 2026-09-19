import { Badge, type badgeVariants } from "@/components/ui/badge";
import type { VariantProps } from "class-variance-authority";

export type ConditionGrade =
  | "mint"
  | "near-mint"
  | "excellent"
  | "bon"
  | "joue"
  | "abime";

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

export function ConditionBadge({ condition, className }: ConditionBadgeProps) {
  return (
    <Badge data-slot="condition-badge" variant={CONDITION_VARIANT[condition]} className={className}>
      {CONDITION_LABELS[condition]}
    </Badge>
  );
}
