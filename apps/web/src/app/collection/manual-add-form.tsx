"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { createCollectionItem } from "@/lib/api/collection";
import { searchCatalog, type CardSearchResult } from "@/lib/api/validation";

const VARIANTS = [
  { value: "normal", label: "Normale" },
  { value: "holo", label: "Holo" },
  { value: "reverse_holo", label: "Reverse holo" },
  { value: "first_edition", label: "1ère édition" },
];

export function ManualAddForm({
  onAdded,
  onCancel,
}: {
  onAdded: () => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CardSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState<CardSearchResult | null>(null);
  const [language, setLanguage] = useState("fr");
  const [variant, setVariant] = useState("normal");
  const [quantity, setQuantity] = useState(1);
  const [conditionGrade, setConditionGrade] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSearch(value: string) {
    setQuery(value);
    setPicked(null);
    if (value.trim().length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      setResults(await searchCatalog(value));
    } finally {
      setSearching(false);
    }
  }

  async function handleSubmit() {
    if (!picked) return;
    setSubmitting(true);
    setError(null);
    try {
      await createCollectionItem({
        card_id: picked.card_id,
        language,
        variant,
        quantity,
        condition_grade: conditionGrade || null,
        purchase_price: purchasePrice || null,
        purchase_currency: purchasePrice ? "EUR" : null,
      });
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "L'ajout a échoué.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="font-heading text-sm font-bold text-foreground">Ajouter une carte</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Sans photo : cherche la carte au catalogue, précise langue, variante et état.
      </p>

      {!picked ? (
        <div className="mt-3">
          <Input
            placeholder="Nom, numéro (ex. 236/217)"
            value={query}
            onChange={(event) => runSearch(event.target.value)}
            aria-label="Chercher une carte au catalogue"
          />
          {searching && <p className="mt-1 text-xs text-muted-foreground">Recherche…</p>}
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
            <div>
              <Label htmlFor="ma-language">Langue</Label>
              <Input
                id="ma-language"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                maxLength={8}
              />
            </div>
            <div>
              <Label htmlFor="ma-variant">Variante</Label>
              <select
                id="ma-variant"
                className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground"
                value={variant}
                onChange={(e) => setVariant(e.target.value)}
              >
                {VARIANTS.map((v) => (
                  <option key={v.value} value={v.value}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="ma-quantity">Quantité</Label>
              <Input
                id="ma-quantity"
                type="number"
                min={1}
                max={50}
                value={quantity}
                onChange={(e) => setQuantity(Number(e.target.value) || 1)}
              />
            </div>
            <div>
              <Label htmlFor="ma-condition">État (facultatif)</Label>
              <Input
                id="ma-condition"
                value={conditionGrade}
                onChange={(e) => setConditionGrade(e.target.value)}
                placeholder="near_mint"
              />
            </div>
            <div className="col-span-2">
              <Label htmlFor="ma-price">Prix d&rsquo;achat en euros (facultatif)</Label>
              <Input
                id="ma-price"
                inputMode="decimal"
                value={purchasePrice}
                onChange={(e) => setPurchasePrice(e.target.value)}
              />
            </div>
          </div>

          {error && <p className="text-sm text-danger-foreground">{error}</p>}

          <div className="flex gap-2">
            <Button type="button" onClick={handleSubmit} disabled={submitting}>
              {submitting ? "Ajout…" : "Ajouter à ma collection"}
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Annuler
            </Button>
          </div>
        </div>
      )}

      {!picked && (
        <div className="mt-3">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Annuler
          </Button>
        </div>
      )}
    </div>
  );
}
