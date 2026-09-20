import { cn } from "@/lib/utils";

const EUR_FORMATTER = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });

// `ValueDelta` (`@/components/value-delta`) affiche un pourcentage : l'agrégat de tête de la
// maquette (« ▲ +42,50 € sur 30 j ») est un montant en euros, jamais un pourcentage — pas la
// même donnée, pas le composant à réutiliser tel quel.
export function TotalValueDelta({ value }: { value: number }) {
  const variant = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const sign = value > 0 ? "+" : "";
  const colorClass = {
    up: "text-success",
    down: "text-danger",
    flat: "text-muted-foreground",
  }[variant];
  const arrow = { up: "▲", down: "▼", flat: "=" }[variant];

  return (
    <span className={cn("inline-flex items-center gap-1 font-mono text-sm font-semibold", colorClass)}>
      {arrow} {sign}
      {EUR_FORMATTER.format(value)}
    </span>
  );
}
