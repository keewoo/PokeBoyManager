"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/empty-state";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import {
  createDeck,
  deleteDeck,
  duplicateDeck,
  fetchDeckAlerts,
  listDecks,
  markDeckAlertsRead,
  type DeckAlert,
  type DeckSummary,
} from "@/lib/api/decks";

function formatLabel(format: DeckSummary["format"]): string {
  return format === "standard" ? "Standard" : format === "expanded" ? "Étendu" : "Illimité";
}

function CreateDeckForm({ onCreated }: { onCreated: (deck: DeckSummary) => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Donne un nom à ton deck.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const deck = await createDeck({ name: trimmed });
      onCreated({
        id: deck.id,
        name: deck.name,
        format: deck.format,
        card_count: deck.legality.card_count,
        legal: deck.legality.legal,
        created_at: deck.created_at,
        updated_at: deck.updated_at,
      });
      // On ouvre tout de suite le constructeur : un deck vide n'a d'intérêt qu'une fois rempli.
      router.push(`/jeu/decks/${deck.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "La création a échoué.");
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="font-heading text-sm font-bold text-foreground">Nouveau deck</h3>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1">
          <Label htmlFor="new-deck-name">Nom du deck</Label>
          <Input
            id="new-deck-name"
            className="mt-1"
            value={name}
            maxLength={120}
            placeholder="Mon deck feu"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") handleSubmit();
            }}
          />
        </div>
        <Button type="button" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Création…" : "Créer et construire"}
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-danger-foreground">{error}</p>}
    </div>
  );
}

function DeckRow({
  deck,
  onDuplicated,
  onDeleted,
}: {
  deck: DeckSummary;
  onDuplicated: (deck: DeckSummary) => void;
  onDeleted: (id: string) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDuplicate() {
    setBusy(true);
    setError(null);
    try {
      const copy = await duplicateDeck(deck.id);
      onDuplicated({
        id: copy.id,
        name: copy.name,
        format: copy.format,
        card_count: copy.legality.card_count,
        legal: copy.legality.legal,
        created_at: copy.created_at,
        updated_at: copy.updated_at,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "La duplication a échoué.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    setBusy(true);
    setError(null);
    try {
      await deleteDeck(deck.id);
      onDeleted(deck.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "La suppression a échoué.");
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-3">
      <div className="min-w-0">
        <Link
          href={`/jeu/decks/${deck.id}`}
          className="font-heading text-sm font-bold text-foreground hover:text-gold"
        >
          {deck.name}
        </Link>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {formatLabel(deck.format)} · {deck.card_count} / 60 cartes
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {deck.legal ? (
          <Badge variant="success">Légal</Badge>
        ) : (
          <Badge variant="danger">À compléter</Badge>
        )}
        <Button asChild size="sm" variant="secondary">
          <Link href={`/jeu/decks/${deck.id}`}>Ouvrir</Link>
        </Button>
        <Button size="sm" variant="outline" onClick={handleDuplicate} disabled={busy}>
          Dupliquer
        </Button>
        {confirming ? (
          <span className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Supprimer&nbsp;?</span>
            <Button size="sm" variant="destructive" onClick={handleDelete} disabled={busy}>
              Confirmer
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirming(false)}
              disabled={busy}
            >
              Annuler
            </Button>
          </span>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setConfirming(true)} disabled={busy}>
            Supprimer
          </Button>
        )}
      </div>
      {error && <p className="w-full text-sm text-danger-foreground">{error}</p>}
    </li>
  );
}

function AlertsNotice({ alerts, onRead }: { alerts: DeckAlert[]; onRead: () => void }) {
  // Notification au joueur (mission point 3) : ce qu'un changement de collection vient de rendre
  // « à compléter », listé sans qu'aucune carte n'ait été retirée d'un deck.
  const decks = Array.from(new Set(alerts.map((a) => a.deck_name)));
  return (
    <div
      role="status"
      data-testid="deck-alerts-notice"
      className="mt-4 rounded-xl border border-[rgba(255,20,147,0.5)] bg-[rgba(255,20,147,0.08)] p-3 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-danger-foreground">
          {alerts.length} carte(s) ont quitté ta collection : {decks.length} deck(s) sont désormais
          à compléter ({decks.join(", ")}).
        </p>
        <Button size="sm" variant="outline" onClick={onRead}>
          Marquer comme lu
        </Button>
      </div>
    </div>
  );
}

export function DecksListView() {
  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<DeckAlert[]>([]);

  useEffect(() => {
    listDecks()
      .then((result) => setDecks(result.decks))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Chargement impossible."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchDeckAlerts(true)
      .then((res) => setAlerts(res.alerts))
      .catch(() => setAlerts([])); // best-effort : la liste des decks reste fiable sans le bandeau
  }, []);

  async function handleMarkRead() {
    try {
      await markDeckAlertsRead();
      setAlerts([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Impossible de marquer les alertes lues.");
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  return (
    <div>
      <h2 className="font-heading text-xl font-bold text-foreground">Mes decks</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Construis un deck avec tes propres cartes, vérifie sa légalité, duplique-le ou exporte-le.
      </p>

      {alerts.length > 0 && <AlertsNotice alerts={alerts} onRead={handleMarkRead} />}

      {error && (
        <div className="mt-3">
          <FormNotice variant="error">{error}</FormNotice>
        </div>
      )}

      <div className="mt-4">
        <CreateDeckForm onCreated={(deck) => setDecks((prev) => [deck, ...prev])} />
      </div>

      {decks.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Aucun deck pour l'instant"
            description="Crée ton premier deck ci-dessus, puis ajoute des cartes de ta collection."
          />
        </div>
      ) : (
        <ul className="mt-4 space-y-2">
          {decks.map((deck) => (
            <DeckRow
              key={deck.id}
              deck={deck}
              onDuplicated={(copy) => setDecks((prev) => [copy, ...prev])}
              onDeleted={(id) => setDecks((prev) => prev.filter((d) => d.id !== id))}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
