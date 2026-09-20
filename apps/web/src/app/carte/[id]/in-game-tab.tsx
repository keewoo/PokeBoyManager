"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/api/client";
import { getInGameStudy, type InGameStudy } from "@/lib/api/cards";

function LegalBadge({ label, legal }: { label: string; legal: boolean | null }) {
  if (legal === null) return null;
  return <Badge variant={legal ? "success" : "danger"}>{label} : {legal ? "légale" : "non légale"}</Badge>;
}

export function InGameTab({ cardId }: { cardId: string }) {
  const [study, setStudy] = useState<InGameStudy | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setStudy(null);
    setError(null);
    getInGameStudy(cardId)
      .then((result) => {
        if (!cancelled) setStudy(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Impossible de charger l'étude en jeu.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cardId]);

  if (error) {
    return <p className="text-sm text-danger-foreground">{error}</p>;
  }

  if (!study) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <LegalBadge label="Standard" legal={study.legalities.standard} />
        <LegalBadge label="Étendu" legal={study.legalities.expanded} />
        {study.prize_rule.applies && <Badge variant="gold">{study.prize_rule.label}</Badge>}
      </div>

      {study.attacks && study.attacks.length > 0 && (
        <div className="space-y-2">
          {study.attacks.map((attack) => (
            <div
              key={attack.name}
              className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2"
            >
              <span className="font-medium text-foreground">{attack.name}</span>
              {attack.damage !== undefined && (
                <span className="font-mono text-sm text-foreground">{attack.damage}</span>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="rounded-md border border-border bg-card p-3">
        <p className="text-sm text-muted-foreground">Présence en tournoi</p>
        {study.tournament_presence.status === "unavailable" ? (
          <p className="mt-1 text-sm text-muted-foreground">Non disponible pour cette carte.</p>
        ) : study.tournament_presence.decks.length === 0 ? (
          <p className="mt-1 text-sm text-foreground">
            Absente des decks de tournoi relevés récemment.
          </p>
        ) : (
          <ul className="mt-1 space-y-1 text-sm text-foreground">
            {study.tournament_presence.decks.map((deck) => (
              <li key={`${deck.deck_name}-${deck.tournament_name}`}>
                {deck.deck_name} — {deck.placement} ({deck.tournament_name})
              </li>
            ))}
          </ul>
        )}
      </div>

      {study.study.status === "no_ai_key" ? (
        <p className="text-sm text-muted-foreground">
          Aucune clé IA configurée : dépose une clé Claude, Gemini ou OpenAI dans ton profil pour
          générer la synthèse de jouabilité.
        </p>
      ) : (
        study.study.text && <p className="text-sm text-foreground">{study.study.text}</p>
      )}
    </div>
  );
}
