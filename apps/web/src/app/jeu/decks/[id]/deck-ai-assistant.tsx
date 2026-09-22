"use client";

import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import {
  proposeDeck,
  type DeckDetail,
  type DeckProposalCorrection,
  type DeckProposalExplanation,
} from "@/lib/api/decks";

// Assistant IA (mission `v7-deck-ia`) : « fais-moi un deck Feu avec mes cartes » évite la page
// blanche. Le joueur donne ses vœux ; l'API propose un deck légal PRIS DANS sa collection, le
// corrige (jamais montré tel quel) puis le réécrit ; l'écran remonte le deck renvoyé au parent
// (une seule vérité de légalité, côté serveur) et affiche la trace des corrections.

// Types du jeu (codes attendus par l'API = `Card.element_type`).
const TYPE_OPTIONS: { code: string; label: string }[] = [
  { code: "grass", label: "Plante" },
  { code: "fire", label: "Feu" },
  { code: "water", label: "Eau" },
  { code: "lightning", label: "Électrik" },
  { code: "psychic", label: "Psy" },
  { code: "fighting", label: "Combat" },
  { code: "darkness", label: "Obscurité" },
  { code: "metal", label: "Métal" },
  { code: "dragon", label: "Dragon" },
  { code: "fairy", label: "Fée" },
  { code: "colorless", label: "Incolore" },
];

export function DeckAiAssistant({
  deckId,
  onProposed,
  disabled,
}: {
  deckId: string;
  onProposed: (deck: DeckDetail) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [style, setStyle] = useState("");
  const [size, setSize] = useState(60);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [explanations, setExplanations] = useState<DeckProposalExplanation[]>([]);
  const [corrections, setCorrections] = useState<DeckProposalCorrection[]>([]);

  const toggleType = useCallback((code: string) => {
    setSelectedTypes((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  }, []);

  const handlePropose = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await proposeDeck(deckId, {
        types: selectedTypes.map((type) => ({ type })),
        style: style.trim() || null,
        size,
      });
      onProposed(response.deck);
      setSummary(response.summary);
      setExplanations(response.explanations);
      setCorrections(response.corrections);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "La proposition a échoué. Réessaie dans un instant."
      );
    } finally {
      setLoading(false);
    }
  }, [deckId, selectedTypes, style, size, onProposed]);

  return (
    <section className="mt-4 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="font-heading text-sm font-bold text-foreground">Assistant IA</h2>
          <p className="text-xs text-muted-foreground">
            Laisse ton IA composer un deck légal avec tes cartes.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="deck-ai-panel"
        >
          {open ? "Masquer" : "Proposer un deck"}
        </Button>
      </div>

      {open && (
        <div id="deck-ai-panel" className="mt-4 space-y-4">
          <fieldset>
            <legend className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
              Types privilégiés
            </legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {TYPE_OPTIONS.map((t) => {
                const active = selectedTypes.includes(t.code);
                return (
                  <button
                    key={t.code}
                    type="button"
                    onClick={() => toggleType(t.code)}
                    aria-pressed={active}
                    className={`rounded-full border px-3 py-1 text-xs font-bold transition ${
                      active
                        ? "border-gold bg-gold/15 text-gold"
                        : "border-input bg-card text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>
          </fieldset>

          <div className="flex flex-wrap items-end gap-4">
            <div className="min-w-56 flex-1">
              <label
                htmlFor="deck-ai-style"
                className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground"
              >
                Style de jeu (facultatif)
              </label>
              <Input
                id="deck-ai-style"
                value={style}
                maxLength={200}
                placeholder="agressif, défensif, contrôle…"
                onChange={(event) => setStyle(event.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <label
                htmlFor="deck-ai-size"
                className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground"
              >
                Taille visée
              </label>
              <Input
                id="deck-ai-size"
                type="number"
                min={40}
                max={60}
                value={size}
                onChange={(event) =>
                  setSize(Math.max(40, Math.min(60, Number(event.target.value) || 60)))
                }
                className="mt-1 w-24"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button onClick={handlePropose} disabled={disabled || loading}>
              {loading ? "L'IA compose…" : "Proposer un deck"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Un seul appel à ton IA — la proposition remplace le contenu du deck.
            </span>
          </div>

          {error && <FormNotice variant="error">{error}</FormNotice>}

          {summary && (
            <div className="rounded-lg border border-border bg-background p-3">
              <p className="text-sm text-foreground">{summary}</p>
            </div>
          )}

          {corrections.length > 0 && (
            <div>
              <p className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
                Ajustements automatiques
              </p>
              <ul className="mt-1 space-y-1 text-xs text-violet-clair">
                {corrections.map((c, i) => (
                  <li key={`${c.code}-${i}`}>• {c.message}</li>
                ))}
              </ul>
            </div>
          )}

          {explanations.length > 0 && (
            <div>
              <p className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
                Pourquoi ces cartes
              </p>
              <ul className="mt-1 space-y-1 text-xs text-muted-foreground">
                {explanations.map((e) => (
                  <li key={e.card_id}>
                    <span className="font-bold text-foreground">
                      {e.quantity}× {e.card_name}
                    </span>{" "}
                    — {e.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
