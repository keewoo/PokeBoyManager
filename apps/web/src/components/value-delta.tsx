import { cn } from "@/lib/utils";

type ValueDeltaVariant = "up" | "down" | "flat";

export type ValueDeltaProps = {
  value: number;
  className?: string;
};

function variantOf(value: number): ValueDeltaVariant {
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

function formatSignedPercent(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const formatted = Math.abs(value).toFixed(1).replace(".", ",");
  return `${sign}${formatted} %`;
}

const VARIANT_CLASS: Record<ValueDeltaVariant, string> = {
  up: "text-success",
  down: "text-danger",
  flat: "text-muted-foreground",
};

export function ValueDelta({ value, className }: ValueDeltaProps) {
  const variant = variantOf(value);

  return (
    <span
      data-slot="value-delta"
      data-variant={variant}
      className={cn(
        "inline-flex items-center font-mono text-sm font-semibold",
        VARIANT_CLASS[variant],
        className
      )}
    >
      {formatSignedPercent(value)}
    </span>
  );
}
