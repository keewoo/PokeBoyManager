"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ValueChartPoint = {
  day: string;
  price: number;
};

export type ValueChartProps = {
  points: ValueChartPoint[];
  /** Prix d'achat de l'exemplaire (mission point 2 : ligne de référence), `null` si inconnu. */
  purchasePrice: number | null;
};

function eur(value: number): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(value);
}

function formatDay(day: string): string {
  return new Date(day).toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: ValueChartPoint }[];
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-sm shadow-md">
      <p className="text-xs text-muted-foreground">
        {new Date(point.day).toLocaleDateString("fr-FR", {
          day: "numeric",
          month: "long",
          year: "numeric",
        })}
      </p>
      <p className="mt-0.5 flex items-center gap-1.5 font-semibold text-foreground">
        <span aria-hidden className="inline-block h-0.5 w-3 rounded-full bg-primary" />
        {eur(point.price)}
      </p>
    </div>
  );
}

export function ValueChart({ points, purchasePrice }: ValueChartProps) {
  if (points.length < 2) {
    return (
      <p className="rounded-md border border-dashed border-border bg-card px-4 py-8 text-center text-sm text-muted-foreground">
        {points.length === 0
          ? "Aucun relevé de prix pour cette période."
          : "Un seul relevé pour l'instant : reviens dans quelques jours pour voir la courbe."}
      </p>
    );
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="day"
            tickFormatter={formatDay}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            minTickGap={24}
          />
          <YAxis
            tickFormatter={(value: number) => eur(value)}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={72}
          />
          <Tooltip content={<ChartTooltip />} />
          {purchasePrice !== null && (
            <ReferenceLine
              y={purchasePrice}
              stroke="var(--muted-foreground)"
              strokeDasharray="4 4"
              label={{
                value: "Prix d'achat",
                position: "insideTopLeft",
                fill: "var(--muted-foreground)",
                fontSize: 12,
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="price"
            stroke="var(--primary)"
            strokeWidth={2}
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 5, fill: "var(--primary)", stroke: "var(--card)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
