"use client";

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { getCardInsights, type CardInsights } from "@/lib/api/cards";

export function HistoryTab({ cardId }: { cardId: string }) {
  const [insights, setInsights] = useState<CardInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInsights(null);
    setError(null);
    getCardInsights(cardId)
      .then((result) => {
        if (!cancelled) setInsights(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Impossible de charger les anecdotes."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cardId]);

  if (error) {
    return <p className="text-sm text-danger-foreground">{error}</p>;
  }

  if (!insights) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  // `status` peut valoir "no_ai_key" alors que des anecdotes déjà générées existent encore
  // (cache expiré, pas de clé pour le regénérer, `pbm_api.insights.service`) : les anecdotes
  // présentes priment toujours sur le statut, jamais masquées derrière un message générique.
  if (insights.anecdotes.length === 0 && insights.status === "no_ai_key") {
    return (
      <p className="text-sm text-muted-foreground">
        Aucune clé IA configurée : dépose une clé Claude, Gemini ou OpenAI dans ton profil pour
        générer les anecdotes de cette carte.
      </p>
    );
  }

  if (insights.anecdotes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Aucune anecdote sourcée trouvée pour cette carte pour l&apos;instant.
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {insights.anecdotes.map((anecdote) => (
        <li key={anecdote.source_url + anecdote.text} className="text-sm text-foreground">
          {anecdote.text}
          <br />
          <a
            href={anecdote.source_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-primary underline"
          >
            Source
          </a>
        </li>
      ))}
    </ul>
  );
}
