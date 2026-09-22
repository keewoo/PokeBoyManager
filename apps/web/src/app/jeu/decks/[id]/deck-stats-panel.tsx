"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ApiError } from "@/lib/api/client";
import { fetchDeckStats, type DeckStatBucket, type DeckStats } from "@/lib/api/decks";

// Couleurs des onze types élémentaires (répartition par type). Sobres, alignées sur les fonds de
// carte (`public/fonds/<code>-01.webp`) — jamais le violet `#9D00FF` en aplat de texte (charte).
const ELEMENT_COLORS: Record<string, string> = {
  grass: "#4CAF50",
  fire: "#FF7043",
  water: "#42A5F5",
  lightning: "#FFCA28",
  psychic: "#AB47BC",
  fighting: "#8D6E63",
  darkness: "#546E7A",
  metal: "#90A4AE",
  dragon: "#7E57C2",
  fairy: "#EC407A",
  colorless: "#BDBDBD",
};

function eur(value: string | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(
    Number(value)
  );
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <p className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-xl font-bold text-foreground">{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

// Barres empilées horizontales pour une répartition (rôle, type de carte) : lisibles sans axe,
// chaque segment porte son libellé et son décompte — pas besoin d'une légende séparée.
function BreakdownBars({ buckets, total }: { buckets: DeckStatBucket[]; total: number }) {
  if (total === 0) return null;
  return (
    <ul className="space-y-1.5">
      {buckets.map((b) => {
        const pct = Math.round((b.count / total) * 100);
        return (
          <li key={b.key}>
            <div className="flex items-baseline justify-between text-sm text-foreground">
              <span>{b.label}</span>
              <span className="text-muted-foreground">
                {b.count} · {pct}%
              </span>
            </div>
            <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ChartTooltip({
  active,
  payload,
  suffix,
}: {
  active?: boolean;
  payload?: { payload: { label: string; count: number } }[];
  suffix: string;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="rounded-md border border-border bg-card px-3 py-2 text-sm shadow-md">
      <p className="font-semibold text-foreground">{point.label}</p>
      <p className="text-xs text-muted-foreground">
        {point.count} {suffix}
      </p>
    </div>
  );
}

function AttackCostChart({ buckets }: { buckets: DeckStatBucket[] }) {
  if (buckets.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border bg-background px-4 py-6 text-center text-sm text-muted-foreground">
        Aucune attaque au catalogue pour les Pokémon de ce deck.
      </p>
    );
  }
  const data = buckets.map((b) => ({ label: b.label, count: b.count }));
  return (
    <div className="h-48 w-full" role="img" aria-label="Courbe des coûts d'attaque">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="label"
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip
            cursor={{ fill: "var(--muted)" }}
            content={<ChartTooltip suffix="attaque(s)" />}
          />
          <Bar dataKey="count" fill="var(--primary)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TypeChart({ buckets }: { buckets: DeckStatBucket[] }) {
  if (buckets.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border bg-background px-4 py-6 text-center text-sm text-muted-foreground">
        Aucun type élémentaire renseigné pour les Pokémon de ce deck.
      </p>
    );
  }
  const data = buckets.map((b) => ({ label: b.label, count: b.count, key: b.key }));
  return (
    <div className="h-48 w-full" role="img" aria-label="Répartition des Pokémon par type">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <XAxis
            dataKey="label"
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            interval={0}
          />
          <YAxis
            allowDecimals={false}
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={28}
          />
          <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip suffix="Pokémon" />} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.key} fill={ELEMENT_COLORS[d.key] ?? "var(--primary)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DeckStatsPanel({ deckId, refreshKey }: { deckId: string; refreshKey: string }) {
  const [stats, setStats] = useState<DeckStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchDeckStats(deckId)
      .then((data) => {
        if (active) setStats(data);
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Statistiques indisponibles.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [deckId, refreshKey]);

  return (
    <section
      aria-label="Statistiques du deck"
      className="mt-4 rounded-lg border border-border bg-card p-4"
      data-testid="deck-stats"
    >
      <h3 className="font-heading text-sm font-bold text-foreground">Statistiques du deck</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Ce que le deck coûte à jouer, ce qu&apos;il contient, ce qu&apos;il vaut — d&apos;après le
        catalogue et les prix relevés, jamais une estimation.
      </p>

      {loading && <p className="mt-3 text-sm text-muted-foreground">Calcul…</p>}
      {error && <p className="mt-3 text-sm text-danger-foreground">{error}</p>}

      {stats && !loading && (
        <div className="mt-3 space-y-5">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="Cartes" value={String(stats.card_count)} hint={`${stats.distinct_cards} distinctes`} />
            <StatTile
              label="PV moyens"
              value={stats.average_hp === null ? "—" : String(stats.average_hp)}
              hint={stats.pokemon_with_hp > 0 ? `sur ${stats.pokemon_with_hp} Pokémon` : undefined}
            />
            <StatTile label="Cartes spéciales" value={String(stats.special_cards)} />
            <StatTile
              label="Valeur"
              value={eur(stats.value.total_eur)}
              hint={
                stats.value.missing_price_cards > 0
                  ? `${stats.value.missing_price_cards} sans prix`
                  : undefined
              }
            />
            <StatTile
              label="Doublons"
              value={`${Math.round(stats.duplicate_ratio * 100)} %`}
              hint={`${stats.duplicate_copies} exemplaire(s)`}
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div>
              <h4 className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
                Par rôle
              </h4>
              <div className="mt-2">
                <BreakdownBars buckets={stats.by_role} total={stats.card_count} />
              </div>
            </div>
            <div>
              <h4 className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
                Par type de carte
              </h4>
              <div className="mt-2">
                <BreakdownBars buckets={stats.by_supertype} total={stats.card_count} />
              </div>
            </div>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <div className="min-w-0">
              <h4 className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
                Coûts d&apos;attaque
              </h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Nombre d&apos;énergies par attaque, pondéré par les exemplaires.
              </p>
              <div className="mt-2">
                <AttackCostChart buckets={stats.attack_cost_curve} />
              </div>
            </div>
            <div className="min-w-0">
              <h4 className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
                Répartition par type
              </h4>
              {stats.untyped_pokemon > 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {stats.untyped_pokemon} Pokémon sans type renseigné (non comptés).
                </p>
              ) : (
                <p className="mt-1 text-xs text-muted-foreground">Types des Pokémon du deck.</p>
              )}
              <div className="mt-2">
                <TypeChart buckets={stats.type_distribution} />
              </div>
            </div>
          </div>

          <div>
            <h4 className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
              Lignes d&apos;évolution
            </h4>
            <div className="mt-2">
              <BreakdownBars
                buckets={stats.stage_distribution}
                total={stats.stage_distribution.reduce((sum, b) => sum + b.count, 0)}
              />
            </div>
            {!stats.has_basic_pokemon && stats.evolution_copies_without_base > 0 && (
              <p className="mt-2 text-sm text-danger-foreground">
                ⚠ {stats.evolution_copies_without_base} carte(s) d&apos;évolution sans aucun Pokémon
                de base : le deck ne peut pas démarrer une partie.
              </p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
