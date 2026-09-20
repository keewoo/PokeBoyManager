"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { DashboardValuePoint } from "@/lib/api/dashboard";

const DATE_FORMATTER = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const EUR_FORMATTER = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

function formatDate(isoDate: string): string {
  return DATE_FORMATTER.format(new Date(isoDate));
}

type CustomTooltipProps = {
  active?: boolean;
  payload?: { value: number; payload: { as_of: string; value: number } }[];
};

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  const point = payload?.[0];
  if (!active || !point) return null;
  return (
    <div className="rounded-md border border-border bg-popover px-3 py-2 text-sm shadow-sm">
      <p className="font-mono font-semibold text-popover-foreground">
        {EUR_FORMATTER.format(point.value)}
      </p>
      <p className="text-xs text-muted-foreground">{formatDate(point.payload.as_of)}</p>
    </div>
  );
}

export type DashboardValueChartProps = {
  points: DashboardValuePoint[];
};

// Un seul point (collection sans historique de 90 j) : Recharts n'a rien à tracer, le chiffre
// du dessus (valeur totale) porte déjà l'information, mieux vaut ne rien afficher qu'un graphe
// vide trompeur.
export function DashboardValueChart({ points }: DashboardValueChartProps) {
  if (points.length < 2) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Historique encore trop court pour tracer une courbe.
      </p>
    );
  }

  const data = points.map((point) => ({
    as_of: point.as_of,
    value: Number(point.total_value_eur),
  }));

  return (
    <div aria-label="Valeur totale de la collection sur 90 jours" role="img" className="h-[200px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="as_of"
            tickFormatter={formatDate}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            minTickGap={32}
          />
          <YAxis
            tickFormatter={(value: number) => EUR_FORMATTER.format(value)}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            axisLine={false}
            tickLine={false}
            width={64}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: "var(--border)" }} />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--primary)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2, fill: "var(--primary)" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
