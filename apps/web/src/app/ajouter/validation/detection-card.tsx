"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  cardImageUrl,
  searchCatalog,
  type CardSearchResult,
  type Detection,
  decoupeDouteuse,
} from "@/lib/api/validation";
import { CardImage } from "@/components/card-image";
import { getApiBaseUrl } from "@/lib/config";
import { cn } from "@/lib/utils";

export type ConfirmForm = {
  language: string;
  variant: string;
  quantity: number;
  conditionGrade: string;
  purchasePrice: string;
};

export type SelectedCard = { card_id: string; name: string; number: string; set_name: string };

const VARIANTS = [
  { value: "normal", label: "Normale" },
  { value: "holo", label: "Holo" },
  { value: "reverse_holo", label: "Reverse holo" },
  { value: "first_edition", label: "1ère édition" },
];

function confidenceLevel(score: number): "low" | "mid" | "high" {
  if (score >= 0.9) return "high";
  if (score >= 0.6) return "mid";
  return "low";
}

function CropImage({ src, className }: { src: string; className: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    // Recadrage introuvable dans le stockage : tuile neutre + message, jamais l'icône « image
    // cassée » (mission `pbm-parcours-validation` point 5 — rien ne doit rester muet à l'écran).
    return (
      <div
        className={cn(
          className,
          "flex items-center justify-center bg-secondary p-1 text-center text-[10px] text-muted-foreground"
        )}
      >
        recadrage indisponible
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element -- image servie par l'API, pas next/image
    <img
      src={src}
      alt="Recadrage de la carte photographiée"
      className={className}
      onError={() => setFailed(true)}
    />
  );
}

function ManualSearch({ onPick }: { onPick: (card: CardSearchResult) => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CardSearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  async function runSearch(value: string) {
    setQuery(value);
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

  return (
    <div className="mt-2 rounded-md border border-border bg-card p-2">
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
                onClick={() => onPick(result)}
              >
                {result.name} · {result.number} · {result.set_name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DetectionCard({
  detection,
  isActive,
  selectedCandidateIndex,
  manualCard,
  form,
  onSelectCandidate,
  onManualCard,
  onFormChange,
  onConfirm,
  onReject,
}: {
  detection: Detection;
  isActive: boolean;
  selectedCandidateIndex: number;
  manualCard: SelectedCard | null;
  form: ConfirmForm;
  onSelectCandidate: (index: number) => void;
  onManualCard: (card: SelectedCard | null) => void;
  onFormChange: (form: ConfirmForm) => void;
  onConfirm: () => void;
  onReject: () => void;
}) {
  const [searchOpen, setSearchOpen] = useState(false);
  const candidates = detection.candidates ?? [];
  const selected = manualCard ?? candidates[selectedCandidateIndex] ?? null;
  const topScore = candidates[0]?.combined_score ?? 0;
  const isPending = detection.status === "pending";
  const isProcessing = detection.extraction === null && detection.status === "pending";

  return (
    <div
      className={cn(
        "det grid grid-cols-[56px_minmax(0,1fr)] gap-3 rounded-lg border border-border bg-card p-3 sm:grid-cols-[64px_minmax(0,1fr)_auto]",
        isActive && isPending && "border-ring ring-2 ring-ring",
        detection.status === "validated" && "opacity-60",
        detection.status === "rejected" && "opacity-40"
      )}
    >
      {/* `self-start` + pile flex : sans ça, la cellule de grille s'étire sur toute la hauteur
          de la carte de validation et `grid-rows-2` imposait cette hauteur aux <img> — avec
          `object-cover`, chaque miniature était zoomée jusqu'à ne montrer qu'une bande de la
          carte (miniatures « coupées » constatées en production). L'aspect 63/88 ne tient que
          si la hauteur reste dérivée de la largeur. */}
      <div className="flex flex-col gap-1 self-start">
        <CropImage
          src={`${getApiBaseUrl()}${detection.crop_url}`}
          className="aspect-[63/88] w-full rounded object-cover"
        />
        {selected && (
          <CardImage
            src={cardImageUrl(selected.card_id)}
            alt="Image officielle du candidat sélectionné"
            className="aspect-[63/88] w-full rounded object-cover"
            label="Pas d'image officielle"
          />
        )}
      </div>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-heading text-sm font-bold text-foreground">
            #{detection.reading_order + 1}
            {detection.extraction?.name ? ` · ${detection.extraction.name}` : ""}
          </span>
          {detection.status === "validated" && <Badge variant="success">validée</Badge>}
          {detection.status === "rejected" && <Badge variant="danger">rejetée</Badge>}
          {detection.identification_method === "visuel" && (
            <Badge variant="success">reconnue sans IA</Badge>
          )}
          {detection.condition?.counterfeit_suspected && (
            <Badge variant="danger">contrefaçon probable</Badge>
          )}
          {decoupeDouteuse(detection) && <Badge variant="danger">découpe douteuse</Badge>}
        </div>

        {decoupeDouteuse(detection) && (
          <p className="mt-1 text-xs text-danger-foreground">
            Le recadrage semble à cheval sur deux cartes : aucun candidat n&apos;est
            présélectionné. Vérifie la vignette avant de choisir, ou reprends la photo.
          </p>
        )}

        {isProcessing && (
          <p className="mt-1 text-sm text-muted-foreground">Identification en cours…</p>
        )}

        {detection.condition?.overall_grade_label && (
          <p className="mt-1 text-xs text-muted-foreground">
            état estimé <span className="font-medium text-foreground">{detection.condition.overall_grade_label}</span>
            {detection.condition.score_10 !== null ? ` (≈ ${detection.condition.score_10}/10)` : ""}
          </p>
        )}

        {!isProcessing && candidates.length === 0 && !manualCard && (
          <p className="mt-1 text-sm text-muted-foreground">
            Aucun candidat trouvé au catalogue — cherche la carte manuellement.
          </p>
        )}

        {candidates.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            confiance{" "}
            <span
              className={cn(
                "font-mono",
                confidenceLevel(topScore) === "high" && "text-success-foreground",
                confidenceLevel(topScore) === "mid" && "text-gold-foreground",
                confidenceLevel(topScore) === "low" && "text-danger-foreground"
              )}
            >
              {Math.round(topScore * 100)} %
            </span>
          </p>
        )}

        {isPending && (
          <>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {candidates.map((candidate, index) => (
                <button
                  key={candidate.card_id}
                  type="button"
                  aria-pressed={!manualCard && selectedCandidateIndex === index}
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-xs",
                    !manualCard && selectedCandidateIndex === index
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-transparent text-foreground hover:bg-accent"
                  )}
                  onClick={() => {
                    onManualCard(null);
                    onSelectCandidate(index);
                  }}
                >
                  {index + 1} · {candidate.name} · {candidate.number}
                </button>
              ))}
              {manualCard && (
                <span className="rounded-full border border-primary bg-primary px-2.5 py-1 text-xs text-primary-foreground">
                  {manualCard.name} · {manualCard.number}
                </span>
              )}
              <button
                type="button"
                className="rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent"
                onClick={() => setSearchOpen((open) => !open)}
              >
                Chercher…
              </button>
            </div>

            {searchOpen && (
              <ManualSearch
                onPick={(card) => {
                  onManualCard({
                    card_id: card.card_id,
                    name: card.name,
                    number: card.number,
                    set_name: card.set_name,
                  });
                  setSearchOpen(false);
                }}
              />
            )}

            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <label className="text-xs text-muted-foreground">
                Langue
                <Input
                  className="mt-1 h-8"
                  value={form.language}
                  onChange={(event) => onFormChange({ ...form, language: event.target.value })}
                  maxLength={8}
                />
              </label>
              <label className="text-xs text-muted-foreground">
                Variante
                <select
                  className="mt-1 h-8 w-full rounded-md border border-input bg-card px-2 text-sm text-foreground"
                  value={form.variant}
                  onChange={(event) => onFormChange({ ...form, variant: event.target.value })}
                >
                  {VARIANTS.map((variant) => (
                    <option key={variant.value} value={variant.value}>
                      {variant.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-muted-foreground">
                Quantité
                <Input
                  className="mt-1 h-8"
                  type="number"
                  min={1}
                  max={20}
                  value={form.quantity}
                  onChange={(event) =>
                    onFormChange({ ...form, quantity: Number(event.target.value) || 1 })
                  }
                />
              </label>
              <label className="text-xs text-muted-foreground">
                État
                <Input
                  className="mt-1 h-8"
                  value={form.conditionGrade}
                  onChange={(event) =>
                    onFormChange({ ...form, conditionGrade: event.target.value })
                  }
                  placeholder="Near mint…"
                />
              </label>
              <label className="text-xs text-muted-foreground">
                Prix d&rsquo;achat (€)
                <Input
                  className="mt-1 h-8"
                  inputMode="decimal"
                  value={form.purchasePrice}
                  onChange={(event) =>
                    onFormChange({ ...form, purchasePrice: event.target.value })
                  }
                  placeholder="0,00"
                />
              </label>
            </div>
          </>
        )}
      </div>

      <div className="col-span-2 flex flex-row items-center justify-end gap-2 sm:col-span-1 sm:flex-col sm:items-end sm:justify-between">
        {isPending && (
          <>
            <Button size="sm" onClick={onConfirm} disabled={!selected}>
              Valider
            </Button>
            <Button size="sm" variant="ghost" onClick={onReject}>
              Rejeter
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
