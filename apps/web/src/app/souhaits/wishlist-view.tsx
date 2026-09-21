"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import { searchCatalog, type CardSearchResult } from "@/lib/api/validation";
import {
  createWishlistItem,
  deleteWishlistItem,
  listWishlist,
  updateWishlistItem,
  type WishlistItem,
} from "@/lib/api/wishlist";

function formatEuros(value: string | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(Number(value));
}

function AddWishlistItem({ onAdded }: { onAdded: (item: WishlistItem) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CardSearchResult[]>([]);
  const [picked, setPicked] = useState<CardSearchResult | null>(null);
  const [targetPrice, setTargetPrice] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(value: string) {
    setQuery(value);
    setPicked(null);
    if (value.trim().length < 2) {
      setResults([]);
      return;
    }
    setResults(await searchCatalog(value));
  }

  async function handleSubmit() {
    if (!picked) return;
    setSubmitting(true);
    setError(null);
    try {
      const item = await createWishlistItem({
        card_id: picked.card_id,
        target_price_eur: targetPrice || null,
        note: note || null,
      });
      onAdded(item);
      setPicked(null);
      setQuery("");
      setResults([]);
      setTargetPrice("");
      setNote("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "Cette carte est déjà dans tes vœux."
          : err instanceof ApiError
            ? err.message
            : "L'ajout a échoué."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="font-heading text-sm font-bold text-foreground">Ajouter un vœu</h3>
      {!picked ? (
        <div className="mt-3">
          <Input
            placeholder="Nom, numéro (ex. 236/217)"
            value={query}
            onChange={(event) => runSearch(event.target.value)}
            aria-label="Chercher une carte au catalogue"
          />
          {results.length > 0 && (
            <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
              {results.map((result) => (
                <li key={result.card_id}>
                  <button
                    type="button"
                    className="w-full rounded-md px-2 py-1 text-left text-xs hover:bg-accent"
                    onClick={() => setPicked(result)}
                  >
                    {result.name} · {result.number} · {result.set_name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
            <span>
              {picked.name} · {picked.number} · {picked.set_name}
            </span>
            <button
              type="button"
              className="text-xs text-muted-foreground underline"
              onClick={() => setPicked(null)}
            >
              Changer
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs text-muted-foreground">
              Prix cible en euros (facultatif)
              <Input
                className="mt-1"
                inputMode="decimal"
                value={targetPrice}
                onChange={(event) => setTargetPrice(event.target.value)}
                placeholder="0,00"
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Note (facultatif)
              <Input
                className="mt-1"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                maxLength={280}
              />
            </label>
          </div>
          {error && <p className="text-sm text-danger-foreground">{error}</p>}
          <Button type="button" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Ajout…" : "Ajouter à mes vœux"}
          </Button>
        </div>
      )}
    </div>
  );
}

function WishlistRow({
  item,
  onChange,
  onRemove,
}: {
  item: WishlistItem;
  onChange: (item: WishlistItem) => void;
  onRemove: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [targetPrice, setTargetPrice] = useState(item.target_price_eur ?? "");
  const [note, setNote] = useState(item.note ?? "");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const updated = await updateWishlistItem(item.id, {
        target_price_eur: targetPrice || null,
        note: note || null,
      });
      onChange(updated);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-3">
      <div className="min-w-0">
        <p className="font-heading text-sm font-bold text-foreground">
          {item.card_name} <span className="font-normal text-muted-foreground">· {item.card_number}</span>
        </p>
        <p className="text-xs text-muted-foreground">
          {item.set_name} ({item.set_code})
        </p>
        {item.note && <p className="mt-1 text-xs text-muted-foreground">{item.note}</p>}
      </div>

      {editing ? (
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-8 w-28"
            inputMode="decimal"
            value={targetPrice}
            onChange={(event) => setTargetPrice(event.target.value)}
            placeholder="Prix cible"
          />
          <Input
            className="h-8 w-40"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Note"
            maxLength={280}
          />
          <Button size="sm" onClick={save} disabled={saving}>
            Enregistrer
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Annuler
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-right">
            <p className="text-sm font-medium text-foreground">
              cible {formatEuros(item.target_price_eur)}
            </p>
            <p className="text-xs text-muted-foreground">marché {formatEuros(item.current_price_eur)}</p>
          </div>
          {item.target_reached === true && <Badge variant="success">objectif atteint</Badge>}
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            Corriger
          </Button>
          <Button size="sm" variant="ghost" onClick={() => onRemove(item.id)}>
            Retirer
          </Button>
        </div>
      )}
    </li>
  );
}

export function WishlistView() {
  const [items, setItems] = useState<WishlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listWishlist()
      .then((result) => setItems(result.items))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Chargement impossible."))
      .finally(() => setLoading(false));
  }, []);

  async function handleRemove(id: string) {
    await deleteWishlistItem(id);
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  return (
    <div>
      <h2 className="font-heading text-xl font-bold text-foreground">Liste de souhaits</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Les cartes que tu veux acheter, avec un prix cible comparé au marché.
      </p>

      {error && (
        <div className="mt-3">
          <FormNotice variant="error">{error}</FormNotice>
        </div>
      )}

      <div className="mt-4">
        <AddWishlistItem onAdded={(item) => setItems((prev) => [item, ...prev])} />
      </div>

      {items.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Aucun vœu pour l'instant"
            description="Cherche une carte ci-dessus pour suivre son prix."
          />
        </div>
      ) : (
        <ul className="mt-4 space-y-2">
          {items.map((item) => (
            <WishlistRow
              key={item.id}
              item={item}
              onChange={(updated) =>
                setItems((prev) => prev.map((i) => (i.id === updated.id ? updated : i)))
              }
              onRemove={handleRemove}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
