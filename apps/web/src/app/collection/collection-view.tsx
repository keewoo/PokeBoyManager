"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { ValueDelta } from "@/components/value-delta";
import { ApiError } from "@/lib/api/client";
import {
  getCollectionFacets,
  listCollection,
  type CollectionAggregates,
  type CollectionFacets,
  type CollectionFilters as Filters,
  type CollectionListItem,
  type CollectionSort,
} from "@/lib/api/collection";
import { cardImageUrl } from "@/lib/api/validation";

import { CollectionFiltersPanel } from "./collection-filters";
import { ManualAddForm } from "./manual-add-form";

const SORT_OPTIONS: { value: CollectionSort; label: string }[] = [
  { value: "value_desc", label: "Valeur ↓" },
  { value: "value_change_30d_desc", label: "Hausse 30 j" },
  { value: "acquired_at_desc", label: "Date d'ajout" },
  { value: "number_asc", label: "Numéro" },
  { value: "name_asc", label: "Nom A→Z" },
];

const MULTI_KEYS = [
  "set_id",
  "series",
  "rarity",
  "card_type",
  "language",
  "variant",
  "condition_grade",
] as const;

function parseFilters(params: URLSearchParams): Filters {
  const filters: Filters = {};
  for (const key of MULTI_KEYS) {
    const values = params.getAll(key);
    if (values.length) filters[key] = values;
  }
  const q = params.get("q");
  if (q) filters.q = q;
  const valueMin = params.get("value_min");
  if (valueMin) filters.value_min = valueMin;
  const valueMax = params.get("value_max");
  if (valueMax) filters.value_max = valueMax;
  const acquiredFrom = params.get("acquired_from");
  if (acquiredFrom) filters.acquired_from = acquiredFrom;
  const acquiredTo = params.get("acquired_to");
  if (acquiredTo) filters.acquired_to = acquiredTo;
  if (params.get("duplicates") === "true") filters.duplicates = true;
  if (params.get("counterfeit") === "true") filters.counterfeit = true;
  const sort = params.get("sort");
  if (sort) filters.sort = sort as CollectionSort;
  return filters;
}

function filtersToSearch(filters: Filters): string {
  const params = new URLSearchParams();
  for (const key of MULTI_KEYS) {
    (filters[key] as string[] | undefined)?.forEach((v) => params.append(key, v));
  }
  if (filters.q) params.set("q", filters.q);
  if (filters.value_min) params.set("value_min", filters.value_min);
  if (filters.value_max) params.set("value_max", filters.value_max);
  if (filters.acquired_from) params.set("acquired_from", filters.acquired_from);
  if (filters.acquired_to) params.set("acquired_to", filters.acquired_to);
  if (filters.duplicates) params.set("duplicates", "true");
  if (filters.counterfeit) params.set("counterfeit", "true");
  if (filters.sort && filters.sort !== "value_desc") params.set("sort", filters.sort);
  return params.toString();
}

function hasActiveFilters(filters: Filters): boolean {
  return Object.entries(filters).some(([key, value]) => key !== "sort" && value !== undefined);
}

function eur(value: string | number): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(
    Number(value)
  );
}

function ItemValueDelta({ value }: { value: string | null }) {
  if (value === null) return null;
  const num = Number(value);
  if (num === 0) return null;
  return <ValueDelta value={num} />;
}

// Les agrégats n'exposent que la variation en euros (mission point 1) ; le pourcentage, seule
// forme montrée par la maquette (`delta()`), se déduit de la valeur totale et de la variation
// sans aller-retour serveur — `null` quand la valeur de référence (totale - variation) est
// nulle ou négative, un pourcentage n'ayant alors pas de sens.
function pctFromEurChange(changeEur: string, totalEur: string): number | null {
  const change = Number(changeEur);
  const base = Number(totalEur) - change;
  if (base <= 0) return null;
  return (change / base) * 100;
}

export function CollectionView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlFilters = useMemo(() => parseFilters(searchParams), [searchParams]);

  const [facets, setFacets] = useState<CollectionFacets | null>(null);
  const [items, setItems] = useState<CollectionListItem[]>([]);
  const [aggregates, setAggregates] = useState<CollectionAggregates | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState(urlFilters.q ?? "");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [addingCard, setAddingCard] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const requestId = useRef(0);

  useEffect(() => {
    getCollectionFacets()
      .then(setFacets)
      .catch(() => {});
  }, [reloadKey]);

  useEffect(() => {
    let cancelled = false;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    listCollection(urlFilters)
      .then((response) => {
        if (cancelled || id !== requestId.current) return;
        setItems(response.items);
        setAggregates(response.aggregates);
        setNextCursor(response.next_cursor);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Impossible de charger la collection.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `urlFilters` dérive de `searchParams`
  }, [searchParams, reloadKey]);

  useEffect(() => {
    const handle = setTimeout(() => {
      if ((searchInput || undefined) !== urlFilters.q) {
        updateFilters({ ...urlFilters, q: searchInput || undefined });
      }
    }, 300);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ne réagit qu'à la saisie, pas à chaque changement d'URL
  }, [searchInput]);

  function updateFilters(next: Filters) {
    const query = filtersToSearch(next);
    router.replace(`/collection${query ? `?${query}` : ""}`);
  }

  function handleReset() {
    setSearchInput("");
    router.replace("/collection");
  }

  async function handleLoadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const response = await listCollection({ ...urlFilters, cursor: nextCursor });
      setItems((prev) => [...prev, ...response.items]);
      setNextCursor(response.next_cursor);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de charger la suite.");
    } finally {
      setLoadingMore(false);
    }
  }

  function handleManualAdded() {
    setAddingCard(false);
    setReloadKey((k) => k + 1);
  }

  const filtered = hasActiveFilters(urlFilters);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-xl font-bold text-foreground">Ma collection</h1>
          {aggregates && (
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>
                <strong className="text-foreground">{aggregates.items_total}</strong> carte
                {aggregates.items_total > 1 ? "s" : ""}
              </span>
              <span>
                <strong className="text-foreground">{eur(aggregates.total_value_eur)}</strong>
              </span>
              {(() => {
                const pct7d = pctFromEurChange(
                  aggregates.value_change_7d_eur,
                  aggregates.total_value_eur
                );
                return pct7d === null ? null : <ValueDelta value={pct7d} />;
              })()}
              <span className="text-xs">7 j</span>
              {(() => {
                const pct30d = pctFromEurChange(
                  aggregates.value_change_30d_eur,
                  aggregates.total_value_eur
                );
                return pct30d === null ? null : <ValueDelta value={pct30d} />;
              })()}
              <span className="text-xs">30 j</span>
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="lg:hidden"
            onClick={() => setDrawerOpen(true)}
          >
            Filtres
          </Button>
          <Button type="button" variant="outline" onClick={() => setAddingCard((v) => !v)}>
            Ajouter une carte
          </Button>
          <Button asChild>
            <Link href="/ajouter">Ajouter des photos</Link>
          </Button>
        </div>
      </div>

      {error && (
        <p role="alert" className="mb-4 rounded-md border border-danger/30 bg-danger-background px-3 py-2 text-sm text-danger-foreground">
          {error}
        </p>
      )}

      {addingCard && (
        <div className="mb-4">
          <ManualAddForm onAdded={handleManualAdded} onCancel={() => setAddingCard(false)} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block">
          <div className="sticky top-4">
            <CollectionFiltersPanel
              facets={facets}
              filters={urlFilters}
              onChange={updateFilters}
              onReset={handleReset}
            />
          </div>
        </aside>

        {drawerOpen && (
          <div className="fixed inset-0 z-50 flex lg:hidden">
            <div className="absolute inset-0 bg-black/50" onClick={() => setDrawerOpen(false)} />
            <div className="relative ml-auto h-full w-[85%] max-w-sm overflow-y-auto bg-background p-4">
              <div className="mb-3 flex items-center justify-between">
                <span className="font-heading text-sm font-bold text-foreground">Filtres</span>
                <Button type="button" variant="ghost" size="sm" onClick={() => setDrawerOpen(false)}>
                  Fermer
                </Button>
              </div>
              <CollectionFiltersPanel
                facets={facets}
                filters={urlFilters}
                onChange={updateFilters}
                onReset={handleReset}
              />
            </div>
          </div>
        )}

        <div>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Input
              className="max-w-sm"
              type="search"
              placeholder="Nom, extension, numéro (ex. 236/217)"
              aria-label="Chercher dans ma collection"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
            <select
              aria-label="Trier"
              className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
              value={urlFilters.sort ?? "value_desc"}
              onChange={(e) =>
                updateFilters({ ...urlFilters, sort: e.target.value as CollectionSort })
              }
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          {loading ? (
            <p className="text-sm text-muted-foreground">Chargement…</p>
          ) : items.length === 0 ? (
            filtered ? (
              <p className="text-sm text-muted-foreground">
                Aucune carte ne correspond à ces filtres.
              </p>
            ) : (
              <EmptyState
                title="Ta collection est vide"
                description="Photographie tes cartes ou ajoute-en une manuellement."
                action={{ label: "Ajouter des photos", href: "/ajouter" }}
              />
            )
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
                {items.map((item) => (
                  <Link
                    key={item.id}
                    href={`/carte/${item.card_id}`}
                    className="group rounded-lg border border-border bg-card p-2 transition-colors hover:border-primary"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element -- image servie par l'API */}
                    <img
                      src={cardImageUrl(item.card_id)}
                      alt={item.card_name}
                      className="aspect-[63/88] w-full rounded object-cover"
                    />
                    <p className="mt-2 truncate text-sm font-semibold text-foreground">
                      {item.card_name}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {item.set_name} · {item.card_number}
                    </p>
                    <div className="mt-1 flex items-center justify-between gap-1">
                      <span className="text-sm font-semibold text-foreground">
                        {item.counterfeit_suspected ? "—" : eur(item.value_eur ?? "0")}
                      </span>
                      {item.counterfeit_suspected ? (
                        <Badge variant="danger">contrefaçon ?</Badge>
                      ) : (
                        <ItemValueDelta value={item.value_change_30d_pct} />
                      )}
                    </div>
                    {item.is_duplicate && (
                      <Badge variant="outline" className="mt-1">
                        doublon
                      </Badge>
                    )}
                  </Link>
                ))}
              </div>

              {nextCursor && (
                <div className="mt-4 flex justify-center">
                  <Button type="button" variant="outline" onClick={handleLoadMore} disabled={loadingMore}>
                    {loadingMore ? "Chargement…" : "Charger plus"}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
