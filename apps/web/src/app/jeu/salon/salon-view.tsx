"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { listDecks, type DeckSummary } from "@/lib/api/decks";
import {
  GAME_EN_COURS,
  listGames,
  type GameSummary,
} from "@/lib/api/games";
import {
  INVITATION_EN_ATTENTE,
  acceptInvitation,
  createInviteLink,
  listReceivedInvitations,
  refuseInvitation,
  type Invitation,
} from "@/lib/api/invitations";
import {
  FILE_APPARIE,
  FILE_EN_ATTENTE,
  checkDeckPlayable,
  enterQueue,
  getPresence,
  getQueue,
  leaveQueue,
  type DeckJouabilite,
  type FileState,
  type Presence,
} from "@/lib/api/matchmaking";
import { getProfile } from "@/lib/api/profile";

// Le plateau de jeu lui-même (reprendre, rejoindre une partie trouvée) est le lot aval
// `j-plateau-layout`, que ce salon débloque : d'ici là, « Reprendre » et « Rejoindre » pointent
// vers la route conventionnelle de la partie. On ne fabrique pas un faux plateau (D9) — le salon
// surface la partie et offre l'entrée en un clic, le plateau la rendra.
function partieHref(gameId: string): string {
  return `/jeu/parties/${gameId}`;
}

/** Les parties en cours, mises en tête : l'action la plus urgente quand elle existe (critère). */
function RepriseSection({ games }: { games: GameSummary[] }) {
  const enCours = games.filter((g) => g.status === GAME_EN_COURS);
  if (enCours.length === 0) return null;
  return (
    <section data-testid="reprise" aria-labelledby="reprise-titre">
      <h3
        id="reprise-titre"
        className="font-heading text-sm font-bold uppercase tracking-[0.08em] text-gold"
      >
        Reprendre une partie
      </h3>
      <ul className="mt-2 space-y-2">
        {enCours.map((game) => (
          <li
            key={game.id}
            data-testid="reprise-game"
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[rgba(255,215,0,0.6)] bg-[rgba(255,215,0,0.08)] p-4"
          >
            <div className="min-w-0">
              <p className="font-heading text-sm font-bold text-foreground">Partie en cours</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Tour {game.current_numero}</p>
            </div>
            <Button asChild>
              <Link href={partieHref(game.id)}>Reprendre</Link>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Choix du deck + jouabilité affichée AVANT l'entrée en file, puis entrée (critère). */
function LancerSection({
  decks,
  onEntered,
  onError,
}: {
  decks: DeckSummary[];
  onEntered: (state: FileState) => void;
  onError: (message: string) => void;
}) {
  const [deckId, setDeckId] = useState<string>(decks[0]?.id ?? "");
  const [jouabilite, setJouabilite] = useState<DeckJouabilite | null>(null);
  const [checking, setChecking] = useState(false);
  const [entering, setEntering] = useState(false);

  // Les decks peuvent arriver après le premier rendu (chargement asynchrone) : on sélectionne alors
  // le premier, sinon le `<select>` resterait sur une valeur vide et la jouabilité ne se calculerait
  // jamais.
  useEffect(() => {
    const premier = decks[0];
    if (!deckId && premier) {
      setDeckId(premier.id);
    }
  }, [deckId, decks]);

  // Dès qu'un deck est choisi, on demande sa jouabilité au serveur (jamais recalculée ici) : le
  // joueur voit s'il peut jouer avant d'entrer, et sinon les cartes en cause (D9).
  useEffect(() => {
    if (!deckId) {
      setJouabilite(null);
      return;
    }
    let active = true;
    setChecking(true);
    setJouabilite(null);
    checkDeckPlayable(deckId)
      .then((result) => {
        if (active) setJouabilite(result);
      })
      .catch((err) => {
        if (active) {
          onError(err instanceof ApiError ? err.message : "Jouabilité indisponible.");
        }
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    return () => {
      active = false;
    };
  }, [deckId, onError]);

  async function handleEnter() {
    if (!deckId) return;
    setEntering(true);
    try {
      const state = await enterQueue(deckId);
      onEntered(state);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Entrée en file impossible.");
      setEntering(false);
    }
  }

  if (decks.length === 0) {
    return (
      <EmptyState
        title="Aucun deck pour jouer"
        description="Construis d'abord un deck jouable, puis reviens lancer une partie."
      />
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1">
          <Label htmlFor="salon-deck">Deck</Label>
          <select
            id="salon-deck"
            data-testid="salon-deck-select"
            className="mt-1 h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground"
            value={deckId}
            onChange={(event) => setDeckId(event.target.value)}
          >
            {decks.map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name}
              </option>
            ))}
          </select>
        </div>
        <Button
          type="button"
          onClick={handleEnter}
          disabled={entering || checking || !jouabilite?.jouable}
        >
          {entering ? "Entrée…" : "Entrer dans la file"}
        </Button>
      </div>

      {/* La jouabilité, affichée avant l'entrée : jouable, ou les cartes refusées nommées. */}
      <div className="mt-3" data-testid="salon-jouabilite" aria-live="polite">
        {checking && <p className="text-xs text-muted-foreground">Vérification du deck…</p>}
        {!checking && jouabilite?.jouable && (
          <Badge variant="success">Deck jouable</Badge>
        )}
        {!checking && jouabilite && !jouabilite.jouable && (
          <div className="rounded-lg border border-[rgba(255,20,147,0.5)] bg-[rgba(255,20,147,0.08)] p-3">
            <p className="text-sm text-danger-foreground">
              Ce deck n&apos;est pas encore jouable :
            </p>
            <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">
              {jouabilite.refus.map((refus, index) => (
                <li key={`${refus.carte}-${index}`}>
                  <span className="text-foreground">{refus.carte}</span> — {refus.raison}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

/** Attente visible et jamais muette : rang, temps, nombre en file, et annulation en un clic. */
function AttenteSection({
  queue,
  onCancelled,
  onError,
}: {
  queue: FileState;
  onCancelled: (state: FileState) => void;
  onError: (message: string) => void;
}) {
  const [cancelling, setCancelling] = useState(false);

  async function handleCancel() {
    setCancelling(true);
    try {
      const state = await leaveQueue();
      onCancelled(state);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Annulation impossible.");
      setCancelling(false);
    }
  }

  return (
    <div
      data-testid="salon-attente"
      role="status"
      aria-live="polite"
      className="rounded-xl border border-[rgba(157,0,255,0.5)] bg-[rgba(157,0,255,0.08)] p-4"
    >
      <p className="font-heading text-sm font-bold text-foreground">Recherche d&apos;un adversaire…</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {queue.joueurs_en_file ?? 1} joueur(s) en file
        {queue.position ? ` · tu es en position ${queue.position}` : ""}
      </p>
      <Button type="button" variant="outline" className="mt-3" onClick={handleCancel} disabled={cancelling}>
        {cancelling ? "Annulation…" : "Annuler la recherche"}
      </Button>
    </div>
  );
}

/** Partie trouvée : on la rejoint en un clic (plateau = lot aval `j-plateau-layout`). */
function ApparieSection({ gameId }: { gameId: string }) {
  return (
    <div
      data-testid="salon-apparie"
      className="rounded-xl border border-[rgba(255,215,0,0.6)] bg-[rgba(255,215,0,0.08)] p-4"
    >
      <p className="font-heading text-sm font-bold text-foreground">Adversaire trouvé !</p>
      <Button asChild className="mt-3">
        <Link href={partieHref(gameId)}>Rejoindre la partie</Link>
      </Button>
    </div>
  );
}

/** Présence, et repli concret quand personne n'est en ligne : inviter, ou s'entraîner (critère). */
function PresenceSection({
  presence,
  onError,
}: {
  presence: Presence;
  onError: (message: string) => void;
}) {
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const personne = presence.autres_disponibles === 0;

  async function handleInvite() {
    setGenerating(true);
    try {
      const lien = await createInviteLink();
      setInviteUrl(lien.url);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Création du lien impossible.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <section data-testid="salon-presence" aria-labelledby="presence-titre">
      <h3
        id="presence-titre"
        className="font-heading text-sm font-bold uppercase tracking-[0.08em] text-gold"
      >
        Qui est là
      </h3>
      <p className="mt-1 text-sm text-muted-foreground">
        {presence.autres_disponibles} joueur(s) disponible(s) · {presence.en_file} en file ·{" "}
        {presence.en_partie} en partie.
      </p>

      {personne && (
        <div className="mt-3 rounded-xl border border-border bg-card p-4">
          <p className="text-sm text-foreground">
            Personne à affronter pour l&apos;instant. Deux façons de jouer quand même :
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button type="button" onClick={handleInvite} disabled={generating}>
              {generating ? "Création…" : "Inviter un ami"}
            </Button>
            {/* Entraînement contre le bot : lot `j-mode-solo`, pas encore livré. On l'annonce
                honnêtement plutôt que d'ouvrir une partie qu'on ne sait pas encore jouer (D9). */}
            <Button type="button" variant="outline" disabled title="Bientôt disponible">
              S&apos;entraîner contre le bot (bientôt)
            </Button>
          </div>
          {inviteUrl && (
            <div className="mt-3" data-testid="salon-invite-lien">
              <Label htmlFor="salon-invite-url">Partage ce lien à ton ami</Label>
              <Input id="salon-invite-url" className="mt-1" readOnly value={inviteUrl} />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/** Les invitations reçues en attente, acceptables ou refusables depuis le salon. */
function InvitationsSection({
  invitations,
  onResolved,
  onError,
}: {
  invitations: Invitation[];
  onResolved: (id: string) => void;
  onError: (message: string) => void;
}) {
  const enAttente = invitations.filter((i) => i.statut === INVITATION_EN_ATTENTE);
  if (enAttente.length === 0) return null;
  return (
    <section data-testid="salon-invitations" aria-labelledby="invitations-titre">
      <h3
        id="invitations-titre"
        className="font-heading text-sm font-bold uppercase tracking-[0.08em] text-gold"
      >
        Invitations reçues
      </h3>
      <ul className="mt-2 space-y-2">
        {enAttente.map((invitation) => (
          <InvitationRow
            key={invitation.id}
            invitation={invitation}
            onResolved={onResolved}
            onError={onError}
          />
        ))}
      </ul>
    </section>
  );
}

function InvitationRow({
  invitation,
  onResolved,
  onError,
}: {
  invitation: Invitation;
  onResolved: (id: string) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function handleAccept() {
    setBusy(true);
    try {
      await acceptInvitation(invitation.id);
      onResolved(invitation.id);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Acceptation impossible.");
      setBusy(false);
    }
  }

  async function handleRefuse() {
    setBusy(true);
    try {
      await refuseInvitation(invitation.id);
      onResolved(invitation.id);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Refus impossible.");
      setBusy(false);
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
      <p className="text-sm text-foreground">
        Un joueur t&apos;invite à jouer{invitation.mode === "lien" ? " (par lien)" : ""}.
      </p>
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" onClick={handleAccept} disabled={busy}>
          Accepter
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={handleRefuse} disabled={busy}>
          Refuser
        </Button>
      </div>
    </li>
  );
}

/** Rappel du dernier résultat : la partie close la plus récente (les parties sont triées desc). */
function DernierResultatSection({ games, userId }: { games: GameSummary[]; userId: string }) {
  const derniere = games.find((g) => g.status !== GAME_EN_COURS);
  if (!derniere) return null;
  const gagne = derniere.vainqueur_user_id === userId;
  const nul = derniere.vainqueur_user_id === null;
  const texte = nul ? "Partie nulle" : gagne ? "Victoire" : "Défaite";
  return (
    <p data-testid="salon-dernier-resultat" className="text-xs text-muted-foreground">
      Dernière partie : <span className="text-foreground">{texte}</span>.
    </p>
  );
}

/**
 * L'écran salon : le point d'où part tout le jeu. Il gate l'accès (D11), met la reprise d'une
 * partie en cours en tête, montre l'état réel de la file, la présence (avec repli concret quand
 * personne n'est là), les invitations reçues et le dernier résultat. Le serveur fait autorité :
 * tout ce qui s'affiche vient d'un appel, aucune règle n'est rejouée ici.
 *
 * Un compte sans droit d'accès au jeu reçoit une **page inexistante** (`notFound()`) : l'API lui
 * répond déjà 404 partout, l'écran ne promet donc aucune porte.
 */
export function SalonView() {
  const [userId, setUserId] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);
  const [accessReady, setAccessReady] = useState(false);

  const [games, setGames] = useState<GameSummary[]>([]);
  const [decks, setDecks] = useState<DeckSummary[]>([]);
  const [queue, setQueue] = useState<FileState | null>(null);
  const [presence, setPresence] = useState<Presence | null>(null);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reportError = useCallback((message: string) => setError(message), []);

  // Étape 1 — autorité d'accès : on lit `game_access` côté serveur. Faux → page inexistante.
  useEffect(() => {
    let active = true;
    getProfile()
      .then((profile) => {
        if (!active) return;
        if (!profile.game_access) {
          setDenied(true);
          return;
        }
        setUserId(profile.id);
      })
      .catch(() => {
        // Une erreur réseau n'est pas un refus d'accès : on ne masque pas le jeu par erreur, on
        // montre le message. Le refus, lui, est explicite (`game_access` faux).
        if (active) setError("Chargement du salon impossible. Réessaie dans un instant.");
      })
      .finally(() => {
        if (active) setAccessReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  // Étape 2 — le contenu, une fois l'accès confirmé.
  useEffect(() => {
    if (!userId) return;
    let active = true;
    listGames()
      .then((g) => active && setGames(g))
      .catch(() => active && setError("Chargement des parties impossible."));
    listDecks()
      .then((res) => active && setDecks(res.decks))
      .catch(() => active && setError("Chargement des decks impossible."));
    getQueue()
      .then((q) => active && setQueue(q))
      .catch(() => active && setError("État de la file indisponible."));
    getPresence()
      .then((p) => active && setPresence(p))
      .catch(() => active && setError("Présence indisponible."));
    listReceivedInvitations()
      .then((inv) => active && setInvitations(inv))
      .catch(() => active && setInvitations([]));
    return () => {
      active = false;
    };
  }, [userId]);

  // Étape 3 — tant qu'on cherche un adversaire, on interroge la file périodiquement : le joueur
  // n'attend jamais devant un écran muet, et passe tout seul à « adversaire trouvé » (principe du
  // jeu). L'intervalle s'arme uniquement en attente, et se coupe dès qu'on en sort.
  useEffect(() => {
    if (queue?.status !== FILE_EN_ATTENTE) return;
    let active = true;
    const timer = setInterval(() => {
      getQueue()
        .then((q) => active && setQueue(q))
        .catch(() => {
          /* transitoire : on retentera au prochain battement, sans masquer de panne durable */
        });
    }, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [queue?.status]);

  if (denied) {
    notFound();
    return null;
  }

  if (!accessReady) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-heading text-xl font-bold text-foreground">Salon de jeu</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Reprends une partie, cherche un adversaire ou invite un ami.
        </p>
      </div>

      {error && <FormNotice variant="error">{error}</FormNotice>}

      <RepriseSection games={games} />

      <section aria-labelledby="jouer-titre">
        <h3
          id="jouer-titre"
          className="font-heading text-sm font-bold uppercase tracking-[0.08em] text-gold"
        >
          Jouer
        </h3>
        <div className="mt-2">
          {queue?.status === FILE_APPARIE && queue.game_id ? (
            <ApparieSection gameId={queue.game_id} />
          ) : queue?.status === FILE_EN_ATTENTE ? (
            <AttenteSection queue={queue} onCancelled={setQueue} onError={reportError} />
          ) : (
            <LancerSection decks={decks} onEntered={setQueue} onError={reportError} />
          )}
        </div>
      </section>

      {presence && <PresenceSection presence={presence} onError={reportError} />}

      <InvitationsSection
        invitations={invitations}
        onResolved={(id) =>
          setInvitations((prev) => prev.filter((invitation) => invitation.id !== id))
        }
        onError={reportError}
      />

      {userId && <DernierResultatSection games={games} userId={userId} />}
    </div>
  );
}
