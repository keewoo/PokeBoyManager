"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  getCardPriceHistory,
  type CardDetail,
  type MyCardItem,
  type PriceHistoryRange,
  type PriceVariant,
} from "@/lib/api/cards";

import { ValueChart } from "./value-chart";

const VARIANT_LABELS: Record<PriceVariant, string> = {
  normal: "Normale",
  holo: "Holo",
  reverse_holo: "Reverse holo",
  first_edition: "Première édition",
};

const RANGES: { value: PriceHistoryRange; label: string }[] = [
  { value: "7", label: "7 j" },
  { value: "30", label: "30 j" },
  { value: "365", label: "1 an" },
  { value: "all", label: "Tout" },
];

function eur(value: string | number): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(
    Number(value)
  );
}

export function ValueTab({
  cardId,
  card,
  primaryItem,
}: {
  cardId: string;
  card: CardDetail;
  primaryItem: MyCardItem | null;
}) {
  const availableVariants = useMemo(
    () =>
      (Object.keys(card.prices_eur) as PriceVariant[]).filter(
        (variant) => card.prices_eur[variant] !== null && card.prices_eur[variant] !== undefined
      ),
    [card.prices_eur]
  );

  const [variant, setVariant] = useState<PriceVariant>(
    (primaryItem?.variant && availableVariants.includes(primaryItem.variant)
      ? primaryItem.variant
      : availableVariants[0]) ?? "normal"
  );
  const [range, setRange] = useState<PriceHistoryRange>("30");
  const [points, setPoints] = useState<{ day: string; price: number }[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPoints(null);
    setError(null);
    getCardPriceHistory(cardId, variant, range)
      .then((response) => {
        if (cancelled) return;
        setPoints(response.points.map((point) => ({ day: point.day, price: Number(point.price_eur) })));
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Impossible de charger la courbe de valeur.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cardId, variant, range]);

  const currentPrice = card.prices_eur[variant];
  // Ligne de référence de la courbe seulement (mission point 2) : la plus-value affichée dans
  // l'en-tête de la fiche compare la valeur réelle de l'exemplaire (état inclus) à son prix
  // d'achat — un second calcul ici, contre le prix catalogue de la variante choisie plutôt que
  // celle réellement possédée, afficherait une plus-value différente pour la même carte.
  const purchasePrice =
    primaryItem?.purchase_price_eur !== null && primaryItem?.purchase_price_eur !== undefined
      ? Number(primaryItem.purchase_price_eur)
      : null;

  if (availableVariants.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Aucun relevé de prix disponible pour cette carte pour l&apos;instant.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-3xl font-bold text-foreground">
            {currentPrice !== null && currentPrice !== undefined ? eur(currentPrice) : "—"}
          </p>
          <p className="text-sm text-muted-foreground">
            tendance Cardmarket · variante {VARIANT_LABELS[variant]}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Variante"
            className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground"
            value={variant}
            onChange={(e) => setVariant(e.target.value as PriceVariant)}
          >
            {availableVariants.map((v) => (
              <option key={v} value={v}>
                {VARIANT_LABELS[v]}
              </option>
            ))}
          </select>
          <div className="flex gap-1" role="group" aria-label="Période">
            {RANGES.map((r) => (
              <Button
                key={r.value}
                type="button"
                size="sm"
                variant={range === r.value ? "default" : "outline"}
                aria-pressed={range === r.value}
                onClick={() => setRange(r.value)}
              >
                {r.label}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {error ? (
        <p className="text-sm text-danger-foreground">{error}</p>
      ) : points === null ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : (
        <ValueChart points={points} purchasePrice={purchasePrice} />
      )}

      <p className="mt-2 text-xs text-muted-foreground">
        Suivi depuis le premier relevé sur cette carte — un historique court en début de vie
        s&apos;affiche tel quel, jamais complété artificiellement.
      </p>
    </div>
  );
}
