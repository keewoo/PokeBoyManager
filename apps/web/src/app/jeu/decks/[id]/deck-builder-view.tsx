"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CardImage } from "@/components/card-image";
import { EmptyState } from "@/components/empty-state";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import {
  DECK_FORMATS,
  SEVERITY_BLOCKING,
  deleteDeck,
  duplicateDeck,
  fetchDeckExport,
  fetchDeckHistory,
  fetchDeckReplacements,
  getDeck,
  getDeckCardFacets,
  removeDeckCard,
  searchDeckCards,
  setDeckCard,
  updateDeck,
  type DeckAlert,
  type DeckCard,
  type DeckCardFacets,
  type DeckCardSearchItem,
  type DeckDetail,
  type DeckFormat,
  type DeckReplacement,
} from "@/lib/api/decks";

import { DeckStatsPanel } from "./deck-stats-panel";

const DECK_SIZE = 60;

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

// -------------------------------------------------------------------- recherche (colonne gauche)

function SearchResultRow({
  item,
  inDeck,
  onAdd,
  disabled,
}: {
  item: DeckCardSearchItem;
  inDeck: number;
  onAdd: (cardId: string) => void;
  disabled: boolean;
}) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-card p-2">
      <CardImage
        src={item.image_url}
        alt={item.name}
        label="Pas d'image"
        className="h-14 w-10 shrink-0 rounded-sm object-cover"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-heading text-sm font-bold text-foreground">{item.name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {item.set_name} · {item.number}
          {item.rarity ? ` · ${item.rarity}` : ""}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {item.is_basic_energy ? (
            <span className="text-violet-clair">Énergie de base — fournie</span>
          ) : (
            <>Possédées : {item.owned_count}</>
          )}
          {inDeck > 0 && <span className="text-gold"> · {inDeck} dans le deck</span>}
        </p>
      </div>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => onAdd(item.card_id)}
        disabled={disabled}
        aria-label={`Ajouter ${item.name} au deck`}
      >
        Ajouter
      </Button>
    </li>
  );
}

function DeckCardSearch({
  deckId,
  deckCardCounts,
  onAdd,
  disabled,
  ownedOnly,
  onOwnedOnlyChange,
}: {
  deckId: string;
  deckCardCounts: Record<string, number>;
  onAdd: (cardId: string) => void;
  disabled: boolean;
  ownedOnly: boolean;
  onOwnedOnlyChange: (value: boolean) => void;
}) {
  const [facets, setFacets] = useState<DeckCardFacets | null>(null);
  const [q, setQ] = useState("");
  const [setId, setSetId] = useState("");
  const [cardType, setCardType] = useState("");
  const [rarity, setRarity] = useState("");
  const [duplicates, setDuplicates] = useState(false);
  const [items, setItems] = useState<DeckCardSearchItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDeckCardFacets()
      .then(setFacets)
      .catch(() => setFacets(null));
  }, []);

  // Recherche débouncée : toute modification de filtre repart de la première page.
  useEffect(() => {
    const handle = setTimeout(() => {
      setLoading(true);
      setError(null);
      searchDeckCards({
        deckId,
        q: q.trim() || undefined,
        setId: setId || undefined,
        cardType: cardType || undefined,
        rarity: rarity || undefined,
        owned: ownedOnly || undefined,
        duplicates: duplicates || undefined,
      })
        .then((page) => {
          setItems(page.items);
          setCursor(page.next_cursor);
        })
        .catch((err) => setError(errorText(err, "La recherche a échoué.")))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [deckId, q, setId, cardType, rarity, ownedOnly, duplicates]);

  async function loadMore() {
    if (!cursor) return;
    setLoading(true);
    try {
      const page = await searchDeckCards({
        deckId,
        q: q.trim() || undefined,
        setId: setId || undefined,
        cardType: cardType || undefined,
        rarity: rarity || undefined,
        owned: ownedOnly || undefined,
        duplicates: duplicates || undefined,
        cursor,
      });
      setItems((prev) => [...prev, ...page.items]);
      setCursor(page.next_cursor);
    } catch (err) {
      setError(errorText(err, "La recherche a échoué."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-label="Recherche de cartes" className="rounded-lg border border-border bg-card p-4">
      <h3 className="font-heading text-sm font-bold text-foreground">Ajouter des cartes</h3>
      <p className="mt-1 text-xs text-muted-foreground">
        Cherche dans le catalogue par nom, numéro, extension, type ou rareté.
      </p>

      <div className="mt-3 space-y-2">
        <Input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Nom ou numéro (ex. Pikachu, 25)"
          aria-label="Chercher une carte au catalogue"
        />
        <div className="flex flex-wrap gap-2">
          <select
            aria-label="Extension"
            className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
            value={setId}
            onChange={(event) => setSetId(event.target.value)}
          >
            <option value="">Toutes les extensions</option>
            {facets?.sets.map((s) => (
              <option key={s.set_id} value={s.set_id}>
                {s.name} ({s.code})
              </option>
            ))}
          </select>
          <select
            aria-label="Type de carte"
            className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
            value={cardType}
            onChange={(event) => setCardType(event.target.value)}
          >
            <option value="">Tous les types</option>
            {facets?.card_types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            aria-label="Rareté"
            className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
            value={rarity}
            onChange={(event) => setRarity(event.target.value)}
          >
            <option value="">Toutes les raretés</option>
            {facets?.rarities.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap gap-4 text-sm text-foreground">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-gold"
              checked={ownedOnly}
              onChange={(event) => onOwnedOnlyChange(event.target.checked)}
            />
            Mes cartes
            {facets ? <span className="text-muted-foreground">({facets.owned_card_count})</span> : null}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-gold"
              checked={duplicates}
              onChange={(event) => setDuplicates(event.target.checked)}
            />
            Doublons
            {facets ? (
              <span className="text-muted-foreground">({facets.duplicate_card_count})</span>
            ) : null}
          </label>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-danger-foreground">{error}</p>}

      {items.length === 0 && !loading ? (
        <p className="mt-4 text-sm text-muted-foreground">Aucune carte ne correspond.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {items.map((item) => (
            <SearchResultRow
              key={item.card_id}
              item={item}
              inDeck={deckCardCounts[item.card_id] ?? 0}
              onAdd={onAdd}
              disabled={disabled}
            />
          ))}
        </ul>
      )}

      {loading && <p className="mt-3 text-xs text-muted-foreground">Recherche…</p>}
      {cursor && !loading && (
        <div className="mt-3">
          <Button type="button" variant="outline" size="sm" onClick={loadMore}>
            Charger plus
          </Button>
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------------- contenu du deck (colonne droite)

function IncompleteAlert({
  card,
  deckId,
  onApplyReplacement,
  onBrowseOwned,
  onRemove,
  disabled,
}: {
  card: DeckCard;
  deckId: string;
  onApplyReplacement: (card: DeckCard, replacement: DeckReplacement) => void;
  onBrowseOwned: () => void;
  onRemove: (cardId: string) => void;
  disabled: boolean;
}) {
  // Suggestions de remplacement : chargées à la demande (mission point 2). On ne remplace JAMAIS
  // en silence — le joueur voit la raison de chaque proposition et clique pour l'appliquer.
  const [suggestions, setSuggestions] = useState<DeckReplacement[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function toggleSuggestions() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (suggestions !== null) return; // déjà chargées
    setLoading(true);
    setError(null);
    try {
      const res = await fetchDeckReplacements(deckId, card.card_id);
      setSuggestions(res.replacements);
    } catch (err) {
      setError(errorText(err, "Impossible de charger des remplacements."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      role="alert"
      className="grid gap-2 rounded-xl border border-[rgba(255,20,147,0.5)] bg-[rgba(255,20,147,0.08)] p-3 text-sm text-danger-foreground"
    >
      <p>
        <b>{card.card_name}</b> : il manque {card.missing} exemplaire(s) dans ta collection — le
        deck reste modifiable mais n’est pas jouable tant qu’il n’est pas complété.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={toggleSuggestions}
          disabled={disabled}
          aria-expanded={open}
        >
          {open ? "Masquer les remplacements" : "Remplacer par une possédée"}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onRemove(card.card_id)}
          disabled={disabled}
        >
          Retirer du deck
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link href={`/carte/${card.card_id}`}>Voir la carte</Link>
        </Button>
      </div>

      {open && (
        <div className="mt-1 grid gap-2" data-testid="replacement-suggestions">
          {loading && <p className="text-xs text-muted-foreground">Recherche de remplacements…</p>}
          {error && <p className="text-xs text-danger-foreground">{error}</p>}
          {suggestions !== null && suggestions.length === 0 && !loading && (
            <p className="text-xs text-muted-foreground">
              Aucune carte possédée du même type à proposer.{" "}
              <button type="button" className="underline" onClick={onBrowseOwned}>
                Chercher moi-même dans mes cartes
              </button>
            </p>
          )}
          {suggestions?.map((suggestion) => (
            <div
              key={suggestion.card_id}
              className="flex items-center gap-3 rounded-lg border border-border bg-card p-2 text-foreground"
            >
              <CardImage
                src={suggestion.image_url}
                alt={suggestion.name}
                label="Pas d'image"
                className="h-12 w-9 shrink-0 rounded-sm object-cover"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate font-heading text-sm font-bold">{suggestion.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {suggestion.reason} · {suggestion.owned_count} possédée(s)
                </p>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onApplyReplacement(card, suggestion)}
                disabled={disabled}
                aria-label={`Remplacer ${card.card_name} par ${suggestion.name}`}
              >
                Remplacer
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DeckCardRow({
  card,
  onSetQuantity,
  onRemoveOne,
  onRemoveCard,
  disabled,
}: {
  card: DeckCard;
  onSetQuantity: (cardId: string, quantity: number) => void;
  onRemoveOne: (card: DeckCard) => void;
  onRemoveCard: (cardId: string) => void;
  disabled: boolean;
}) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-card p-2">
      <CardImage
        src={card.image_url}
        alt={card.card_name}
        label="Pas d'image"
        className="h-14 w-10 shrink-0 rounded-sm object-cover"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-heading text-sm font-bold text-foreground">{card.card_name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {card.set_name} · {card.card_number}
        </p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {card.is_basic_energy && <Badge variant="default">Énergie de base</Badge>}
          {card.missing > 0 && <Badge variant="danger">Non possédée ({card.missing})</Badge>}
          {!card.in_format && <Badge variant="danger">Hors format</Badge>}
          {card.counterfeit_excluded > 0 && (
            <Badge variant="danger">Contrefaçon exclue ({card.counterfeit_excluded})</Badge>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button
          size="icon"
          variant="outline"
          onClick={() => onRemoveOne(card)}
          disabled={disabled}
          aria-label={`Retirer un exemplaire de ${card.card_name}`}
        >
          −
        </Button>
        <Input
          type="number"
          min={0}
          max={DECK_SIZE}
          value={card.quantity}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (!Number.isFinite(next)) return;
            onSetQuantity(card.card_id, Math.max(0, Math.min(DECK_SIZE, Math.floor(next))));
          }}
          aria-label={`Quantité de ${card.card_name}`}
          className="h-11 w-16 px-2 text-center"
        />
        <Button
          size="icon"
          variant="outline"
          onClick={() => onSetQuantity(card.card_id, card.quantity + 1)}
          disabled={disabled}
          aria-label={`Ajouter un exemplaire de ${card.card_name}`}
        >
          +
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => onRemoveCard(card.card_id)}
          disabled={disabled}
          aria-label={`Retirer ${card.card_name} du deck`}
        >
          Retirer
        </Button>
      </div>
    </li>
  );
}

function DeckContents({
  deck,
  onSetQuantity,
  onRemoveOne,
  onRemoveCard,
  onApplyReplacement,
  onBrowseOwned,
  disabled,
}: {
  deck: DeckDetail;
  onSetQuantity: (cardId: string, quantity: number) => void;
  onRemoveOne: (card: DeckCard) => void;
  onRemoveCard: (cardId: string) => void;
  onApplyReplacement: (card: DeckCard, replacement: DeckReplacement) => void;
  onBrowseOwned: () => void;
  disabled: boolean;
}) {
  const incomplete = deck.cards.filter((c) => c.missing > 0);
  // Constats globaux (taille, Pokémon de base, limite des 4) : les constats « non possédée » de
  // chaque carte sont déjà rendus par l'alerte « à compléter » ci-dessous — on ne les redouble pas.
  const globalIssues = deck.legality.issues.filter((i) => i.code !== "not_owned");

  return (
    <section aria-label="Contenu du deck" className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="font-heading text-sm font-bold text-foreground">
          Deck · {deck.legality.card_count} / {DECK_SIZE}
        </h3>
        {deck.legality.legal ? (
          <Badge variant="success">Légal ✓</Badge>
        ) : (
          <Badge variant="danger">Illégal</Badge>
        )}
      </div>

      {deck.legality.legal ? (
        <p className="mt-2 text-sm text-success-foreground">
          Ce deck est légal en format {deck.legality.format_label} : tu peux jouer avec.
        </p>
      ) : (
        globalIssues.length > 0 && (
          <ul className="mt-2 space-y-1">
            {globalIssues.map((issue, index) => (
              <li
                key={`${issue.code}-${index}`}
                className={
                  issue.severity === SEVERITY_BLOCKING
                    ? "text-sm text-danger-foreground"
                    : "text-sm text-muted-foreground"
                }
              >
                {issue.severity === SEVERITY_BLOCKING ? "⛔ " : "⚠ "}
                {issue.message}
              </li>
            ))}
          </ul>
        )
      )}

      {incomplete.length > 0 && (
        <div className="mt-3 space-y-2">
          {incomplete.map((card) => (
            <IncompleteAlert
              key={card.card_id}
              card={card}
              deckId={deck.id}
              onApplyReplacement={onApplyReplacement}
              onBrowseOwned={onBrowseOwned}
              onRemove={onRemoveCard}
              disabled={disabled}
            />
          ))}
        </div>
      )}

      {deck.cards.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Deck vide"
            description="Ajoute des cartes depuis la recherche à gauche pour commencer."
          />
        </div>
      ) : (
        <ul className="mt-3 space-y-2">
          {deck.cards.map((card) => (
            <DeckCardRow
              key={card.card_id}
              card={card}
              onSetQuantity={onSetQuantity}
              onRemoveOne={onRemoveOne}
              onRemoveCard={onRemoveCard}
              disabled={disabled}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

// -------------------------------------------------------------------------------- vue principale

export function DeckBuilderView({ deckId }: { deckId: string }) {
  const router = useRouter();
  const [deck, setDeck] = useState<DeckDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);
  const [name, setName] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [ownedOnly, setOwnedOnly] = useState(false);
  const searchRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    getDeck(deckId)
      .then((detail) => {
        setDeck(detail);
        setName(detail.name);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setError(errorText(err, "Chargement impossible."));
        }
      })
      .finally(() => setLoading(false));
  }, [deckId]);

  const deckCardCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const card of deck?.cards ?? []) counts[card.card_id] = card.quantity;
    return counts;
  }, [deck]);

  // Toute mutation renvoie le deck recalculé (légalité comprise) : on remplace l'état entier
  // plutôt que de le corriger à la main — jamais deux vérités de légalité, une côté serveur, une
  // devinée côté écran.
  const runMutation = useCallback(
    async (op: () => Promise<DeckDetail>, fallback: string) => {
      setMutating(true);
      setError(null);
      try {
        const updated = await op();
        setDeck(updated);
      } catch (err) {
        setError(errorText(err, fallback));
      } finally {
        setMutating(false);
      }
    },
    []
  );

  const handleAdd = useCallback(
    (cardId: string) => {
      const current = deckCardCounts[cardId] ?? 0;
      void runMutation(() => setDeckCard(deckId, cardId, current + 1), "L'ajout a échoué.");
    },
    [deckCardCounts, deckId, runMutation]
  );

  const handleSetQuantity = useCallback(
    (cardId: string, quantity: number) => {
      if (quantity <= 0) {
        void runMutation(() => removeDeckCard(deckId, cardId), "Le retrait a échoué.");
      } else {
        void runMutation(() => setDeckCard(deckId, cardId, quantity), "La mise à jour a échoué.");
      }
    },
    [deckId, runMutation]
  );

  const handleRemoveOne = useCallback(
    (card: DeckCard) => {
      // « Retirer un exemplaire » : décrémente, et retire la carte quand c'était le dernier.
      if (card.quantity <= 1) {
        void runMutation(() => removeDeckCard(deckId, card.card_id), "Le retrait a échoué.");
      } else {
        void runMutation(
          () => setDeckCard(deckId, card.card_id, card.quantity - 1),
          "Le retrait a échoué."
        );
      }
    },
    [deckId, runMutation]
  );

  const handleRemoveCard = useCallback(
    (cardId: string) => {
      // « Retirer la carte » : supprime tous les exemplaires d'un coup.
      void runMutation(() => removeDeckCard(deckId, cardId), "Le retrait a échoué.");
    },
    [deckId, runMutation]
  );

  const handleBrowseOwned = useCallback(() => {
    // Repli « Chercher moi-même » : on bascule la recherche sur les cartes possédées et on y amène
    // l'utilisateur, qui choisit lui-même — jamais d'échange en silence.
    setOwnedOnly(true);
    searchRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const handleApplyReplacement = useCallback(
    (card: DeckCard, replacement: DeckReplacement) => {
      // Échange EXPLICITE, demandé par le joueur : on ajoute la carte possédée à la même quantité
      // que celle qui manquait, puis on retire la carte manquante. Deux écritures, jamais en
      // silence — le résultat renvoyé par la seconde reflète les deux.
      const current = deckCardCounts[replacement.card_id] ?? 0;
      void runMutation(async () => {
        await setDeckCard(deckId, replacement.card_id, current + card.quantity);
        return removeDeckCard(deckId, card.card_id);
      }, "Le remplacement a échoué.");
    },
    [deckCardCounts, deckId, runMutation]
  );

  function commitName() {
    const trimmed = name.trim();
    if (!deck || !trimmed || trimmed === deck.name) {
      setName(deck?.name ?? "");
      return;
    }
    void runMutation(() => updateDeck(deckId, { name: trimmed }), "Le renommage a échoué.");
  }

  function changeFormat(format: DeckFormat) {
    void runMutation(() => updateDeck(deckId, { format }), "Le changement de format a échoué.");
  }

  async function handleDuplicate() {
    setMutating(true);
    setError(null);
    try {
      const copy = await duplicateDeck(deckId);
      router.push(`/jeu/decks/${copy.id}`);
    } catch (err) {
      setError(errorText(err, "La duplication a échoué."));
      setMutating(false);
    }
  }

  async function handleExport(fmt: "text" | "pdf") {
    try {
      const { blob, filename } = await fetchDeckExport(deckId, fmt);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorText(err, "L'export a échoué."));
    }
  }

  async function handleDeleteDeck() {
    setMutating(true);
    setError(null);
    try {
      await deleteDeck(deckId);
      // Suppression définitive côté API. Une partie en cours ne doit pas perdre son deck : la
      // file d'attente / la partie (lots `v7` à venir) devront figer une copie du deck à son
      // démarrage — il n'existe encore aucune table de partie dans ce dépôt à protéger ici.
      router.push("/jeu/decks");
    } catch (err) {
      setError(errorText(err, "La suppression a échoué."));
      setMutating(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  if (notFound) {
    return (
      <EmptyState
        title="Deck introuvable"
        description="Ce deck n'existe pas ou ne t'appartient pas."
        action={{ label: "Retour à mes decks", href: "/jeu/decks" }}
      />
    );
  }

  if (!deck) {
    return (
      <FormNotice variant="error">{error ?? "Chargement impossible."}</FormNotice>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <Link href="/jeu/decks" className="hover:text-foreground">
          ← Mes decks
        </Link>
      </div>

      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-56 flex-1">
          <label className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
            Nom du deck
          </label>
          <Input
            value={name}
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            onBlur={commitName}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
            }}
            aria-label="Nom du deck"
            className="mt-1"
          />
        </div>
        <div>
          <label
            htmlFor="deck-format"
            className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground"
          >
            Format
          </label>
          <select
            id="deck-format"
            className="mt-1 flex h-12 rounded-full border border-input bg-card px-4 text-sm text-foreground"
            value={deck.format}
            onChange={(event) => changeFormat(event.target.value as DeckFormat)}
          >
            {DECK_FORMATS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={handleDuplicate} disabled={mutating}>
          Dupliquer
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleExport("text")}>
          Exporter (texte)
        </Button>
        <Button variant="outline" size="sm" onClick={() => handleExport("pdf")}>
          Exporter (PDF)
        </Button>
        {confirmingDelete ? (
          <span className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Supprimer ce deck&nbsp;?</span>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDeleteDeck}
              disabled={mutating}
            >
              Confirmer
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmingDelete(false)}>
              Annuler
            </Button>
          </span>
        ) : (
          <Button variant="ghost" size="sm" onClick={() => setConfirmingDelete(true)}>
            Supprimer
          </Button>
        )}
      </div>

      {error && (
        <div className="mt-3">
          <FormNotice variant="error">{error}</FormNotice>
        </div>
      )}

      <div ref={searchRef} className="mt-4 grid gap-4 lg:grid-cols-2">
        <DeckCardSearch
          deckId={deckId}
          deckCardCounts={deckCardCounts}
          onAdd={handleAdd}
          disabled={mutating}
          ownedOnly={ownedOnly}
          onOwnedOnlyChange={setOwnedOnly}
        />
        <DeckContents
          deck={deck}
          onSetQuantity={handleSetQuantity}
          onRemoveOne={handleRemoveOne}
          onRemoveCard={handleRemoveCard}
          onApplyReplacement={handleApplyReplacement}
          onBrowseOwned={handleBrowseOwned}
          disabled={mutating}
        />
      </div>

      <DeckStatsPanel deckId={deckId} refreshKey={deck.updated_at} />
      <DeckHistory deckId={deckId} refreshKey={deck.updated_at} />
    </div>
  );
}

function DeckHistory({ deckId, refreshKey }: { deckId: string; refreshKey: string }) {
  // Historique des changements de collection ayant touché ce deck (mission « historique des
  // modifications du deck »). Chargé à l'ouverture ; rechargé quand le deck change (`refreshKey`).
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<DeckAlert[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError(null);
    fetchDeckHistory(deckId)
      .then((res) => {
        if (active) setEvents(res.events);
      })
      .catch((err) => {
        if (active) setError(errorText(err, "Impossible de charger l'historique."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, deckId, refreshKey]);

  return (
    <section className="mt-4 rounded-lg border border-border bg-card p-4">
      <button
        type="button"
        className="flex w-full items-center justify-between font-heading text-sm font-bold text-foreground"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>Historique des changements de collection</span>
        <span aria-hidden>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="mt-3 text-sm" data-testid="deck-history">
          {loading && <p className="text-muted-foreground">Chargement…</p>}
          {error && <p className="text-danger-foreground">{error}</p>}
          {events !== null && events.length === 0 && !loading && (
            <p className="text-muted-foreground">
              Aucun changement : aucune carte de ce deck n’a quitté ta collection.
            </p>
          )}
          {events && events.length > 0 && (
            <ul className="space-y-2">
              {events.map((event) => (
                <li key={event.id} className="rounded-md border border-border bg-background p-2">
                  <p className="text-foreground">
                    <b>{event.card_name}</b> —{" "}
                    {event.reason === "counterfeit"
                      ? "signalée contrefaçon (exclue du décompte)"
                      : "exemplaire retiré de la collection"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Il en manque {event.missing} ({event.owned}/{event.required} possédée(s)) ·{" "}
                    {new Date(event.created_at).toLocaleDateString("fr-FR")}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
