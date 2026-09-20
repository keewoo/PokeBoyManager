"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/empty-state";
import { ValueDelta } from "@/components/value-delta";
import { ApiError } from "@/lib/api/client";
import { getDashboard, type DashboardMoverCard, type DashboardResponse } from "@/lib/api/dashboard";
import { getProfile, type ProfileResponse } from "@/lib/api/profile";
import { cardImageUrl } from "@/lib/api/validation";

import { DashboardValueChart } from "./value-chart";
import { TotalValueDelta } from "./total-value-delta";

const EUR_FORMATTER = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const DATE_FORMATTER = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

function eur(value: string | number): string {
  return EUR_FORMATTER.format(Number(value));
}

function MoverRow({ mover }: { mover: DashboardMoverCard }) {
  return (
    <Link
      href={`/carte/${mover.card_id}`}
      className="flex items-center gap-3 rounded-md p-2 transition-colors hover:bg-secondary"
    >
      {/* eslint-disable-next-line @next/next/no-img-element -- image servie par l'API */}
      <img
        src={cardImageUrl(mover.card_id)}
        alt={mover.card_name}
        className="h-14 w-10 shrink-0 rounded object-cover"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{mover.card_name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {mover.set_name} · {mover.card_number}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className="font-mono text-sm font-semibold text-foreground">{eur(mover.value_eur)}</p>
        {mover.value_change_30d_pct !== null && <ValueDelta value={Number(mover.value_change_30d_pct)} />}
      </div>
    </Link>
  );
}

export function DashboardView() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getDashboard(), getProfile()])
      .then(([dashboardResponse, profileResponse]) => {
        setDashboard(dashboardResponse);
        setProfile(profileResponse);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Impossible de charger le tableau de bord.");
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  if (error || !dashboard) {
    return (
      <p
        role="alert"
        className="rounded-md border border-danger/30 bg-danger-background px-3 py-2 text-sm text-danger-foreground"
      >
        {error ?? "Impossible de charger le tableau de bord."}
      </p>
    );
  }

  const dateLabel = DATE_FORMATTER.format(new Date());
  const greetingName = profile?.pseudo ?? profile?.first_name ?? profile?.last_name ?? "";

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="font-mono text-xs font-semibold uppercase text-muted-foreground">
            {dateLabel}
          </span>
          <h1 className="mt-1 font-heading text-2xl font-bold text-foreground">
            Salut {greetingName}
          </h1>
        </div>
        <Button asChild>
          <Link href="/ajouter">Ajouter des photos</Link>
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-border bg-card p-4">
          <span className="font-mono text-xs font-semibold uppercase text-muted-foreground">
            Valeur de la collection · {dashboard.items_priced} carte
            {dashboard.items_priced > 1 ? "s" : ""} cotée{dashboard.items_priced > 1 ? "s" : ""}
          </span>
          <p className="mt-1 font-heading text-4xl font-extrabold text-foreground">
            {eur(dashboard.total_value_eur)}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <TotalValueDelta value={Number(dashboard.value_change_30d_eur)} />
            <span>sur 30 j</span>
            {dashboard.items_missing_price > 0 && (
              <span>
                · {dashboard.items_missing_price} carte{dashboard.items_missing_price > 1 ? "s" : ""} non
                cotée{dashboard.items_missing_price > 1 ? "s" : ""}
              </span>
            )}
          </div>
          <div className="mt-3">
            <DashboardValueChart points={dashboard.value_history} />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Historique construit par les relevés quotidiens.
          </p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-2 font-heading text-sm font-bold text-foreground">
            Plus fortes variations · 30 j
          </h2>
          {dashboard.top_movers.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Pas encore assez d&apos;historique pour calculer des variations.
            </p>
          ) : (
            <div className="grid gap-1">
              {dashboard.top_movers.map((mover) => (
                <MoverRow key={mover.item_id} mover={mover} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-border bg-card p-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-heading text-sm font-bold text-foreground">Derniers ajouts</h2>
          <Link href="/collection" className="text-sm font-medium text-primary hover:underline">
            Toute la collection
          </Link>
        </div>
        {dashboard.recent_additions.length === 0 ? (
          <EmptyState
            title="Ta collection est vide"
            description="Photographie tes cartes ou ajoute-en une manuellement."
            action={{ label: "Ajouter des photos", href: "/ajouter" }}
          />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
            {dashboard.recent_additions.map((addition) => (
              <Link
                key={addition.item_id}
                href={`/carte/${addition.card_id}`}
                className="group rounded-lg border border-border bg-card p-2 transition-colors hover:border-primary"
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- image servie par l'API */}
                <img
                  src={cardImageUrl(addition.card_id)}
                  alt={addition.card_name}
                  className="aspect-[63/88] w-full rounded object-cover"
                />
                <p className="mt-2 truncate text-sm font-semibold text-foreground">
                  {addition.card_name}
                </p>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
