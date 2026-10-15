"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";
import {
  getMesStatistiques,
  libelleDuree,
  libelleTaux,
  listMesParties,
  phraseNonSignificatif,
  type FiltresParties,
  type HistoriqueParties,
  type PartieJouee,
  type StatistiquesJoueur,
  type StatsAdversaire,
  type StatsDeck,
  type Taux,
} from "@/lib/api/stats-joueur";
import { raisonCourte } from "@/lib/game/fin";

// Écran « Mes parties » (lot `j-stats-joueur`, jalon J4).
//
// Trois blocs, dans l'ordre où on les lit : ce que mon compte totalise, ce que chaque deck donne,
// puis la liste des parties avec leur replay. Les agrégats portent sur **tout** l'historique, la
// liste seule est paginée — un taux qui changerait en cliquant « suivant » serait pire qu'absent.
//
// **Aucun taux n'est affiché nu.** `phraseNonSignificatif` accompagne chaque pourcentage calculé
// sur moins de parties que le seuil du serveur : c'est le risque nommé du lot (« des statistiques
// flatteuses calculées sur trois parties trompent le joueur sur son deck »). L'écran ne décide pas
// du seuil, il le reçoit.

/** Les libellés des trois résultats, pour la liste et le filtre. */
const RESULTATS: Record<string, string> = {
  victoire: "Victoire",
  defaite: "Défaite",
  egalite: "Égalité",
};

/** Date et heure courtes d'une partie finie. */
function quand(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Un chiffre mis en avant, avec sa légende et son éventuelle mise en garde. */
function Tuile({
  libelle,
  valeur,
  precision,
}: {
  libelle: string;
  valeur: string;
  precision?: string | null;
}) {
  return (
    <div className="rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3">
      <p className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
        {libelle}
      </p>
      <p className="mt-1 text-2xl font-bold text-foreground">{valeur}</p>
      {precision ? <p className="mt-1 text-xs text-muted-foreground">{precision}</p> : null}
    </div>
  );
}

/**
 * Un taux de victoire et, quand il n'est pas significatif, la phrase qui le dit.
 *
 * Le pourcentage reste affiché (le masquer ressemblerait à une panne) mais en sourdine, et la
 * phrase chiffre ce qui manque. `data-significatif` existe pour que le test puisse vérifier que la
 * mise en garde est réellement posée, pas seulement calculée.
 */
function TauxVictoire({ taux, libelle }: { taux: Taux; libelle: string }) {
  const avertissement = phraseNonSignificatif(taux);
  return (
    <div data-testid="taux" data-significatif={taux.significatif ? "oui" : "non"}>
      <p className="font-heading text-xs font-bold uppercase tracking-[0.13em] text-muted-foreground">
        {libelle}
      </p>
      <p
        className={`mt-1 text-2xl font-bold ${
          taux.significatif ? "text-foreground" : "text-muted-foreground"
        }`}
      >
        {libelleTaux(taux)}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {taux.victoires} V · {taux.defaites} D · {taux.egalites} N
      </p>
      {avertissement ? (
        <p data-testid="non-significatif" className="mt-1 text-xs text-[#C77DFF]">
          {avertissement}
        </p>
      ) : null}
    </div>
  );
}

/** Le nom d'un adversaire : son pseudo, « le bot » pour l'entraînement, « ? » sinon. */
function nomAdversaire(adversaire: Pick<StatsAdversaire, "bot" | "pseudo">): string {
  if (adversaire.bot) return "Entraînement (bot)";
  return adversaire.pseudo ?? "Adversaire inconnu";
}

/** Le nom d'un deck, ou la mention explicite d'un deck effacé depuis. */
function nomDeck(deck: Pick<StatsDeck, "deck_id" | "deck_nom">): string {
  return deck.deck_nom ?? (deck.deck_id === null ? "Deck supprimé" : "Deck sans nom");
}

/** La fiche d'un deck dans le tableau : son bilan, et contre qui il gagne. */
function LigneDeck({ deck }: { deck: StatsDeck }) {
  return (
    <li
      data-testid="deck"
      data-deck-id={deck.deck_id ?? "supprime"}
      className="rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="font-heading text-sm font-semibold">{nomDeck(deck)}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {deck.taux.parties} partie{deck.taux.parties > 1 ? "s" : ""} · durée moyenne{" "}
            {libelleDuree(deck.duree_moyenne_s)}
          </p>
        </div>
        <TauxVictoire taux={deck.taux} libelle="Victoires" />
      </div>
      {deck.adversaires.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 border-t border-[rgba(157,0,255,0.2)] pt-3">
          {deck.adversaires.map((adversaire) => (
            <li
              key={`${adversaire.user_id ?? "bot"}`}
              data-testid="deck-adversaire"
              className="flex flex-wrap items-baseline justify-between gap-2 text-sm"
            >
              <span>{nomAdversaire(adversaire)}</span>
              <span className="text-muted-foreground">
                {libelleTaux(adversaire.taux)} sur {adversaire.taux.parties} partie
                {adversaire.taux.parties > 1 ? "s" : ""}
                {adversaire.taux.significatif ? "" : " (trop peu pour conclure)"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Une partie dans la liste : ce qu'elle a donné, et le lien vers son replay s'il existe. */
function LignePartie({ partie }: { partie: PartieJouee }) {
  return (
    <li
      data-testid="partie"
      data-resultat={partie.resultat}
      className="flex flex-wrap items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3"
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm">
          <strong>{RESULTATS[partie.resultat] ?? partie.resultat}</strong>
          {" contre "}
          {partie.adversaire_bot
            ? "le bot"
            : (partie.adversaire_pseudo ?? "un adversaire inconnu")}
          {partie.deck_nom ? ` · ${partie.deck_nom}` : ""}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {quand(partie.finie_a)} · {raisonCourte(partie.raison_fin)} ·{" "}
          {libelleDuree(partie.duree_s)}
          {/* Une partie qui ne compte pas doit le dire : sinon un joueur qui recompte ses
              victoires à la main ne comprend pas l'écart avec le total affiché plus haut. */}
          {!partie.comptabilisee && (
            <span data-testid="hors-compte">
              {" "}
              · {partie.entrainement ? "entraînement, ne compte pas" : "ne compte pour personne"}
            </span>
          )}
        </p>
      </div>
      {partie.replay_disponible ? (
        <Link
          href={`/jeu/parties/${partie.game_id}/replay`}
          data-testid="lien-replay"
          className="text-sm text-[#C77DFF] underline"
        >
          Revoir la partie
        </Link>
      ) : (
        // La purge efface la partie, pas sa trace : on l'explique au lieu de proposer un lien
        // qui répondrait 404 — ce qu'un joueur lirait comme une panne.
        <span data-testid="replay-absent" className="text-xs text-muted-foreground">
          Replay effacé
        </span>
      )}
    </li>
  );
}

/** Nombre de parties par page de l'historique (le serveur plafonne à 100). */
const PAR_PAGE = 20;

/**
 * Écran « Mes parties » : mes totaux, mes decks, mes adversaires, et l'historique paginé.
 *
 * Les deux appels (agrégats et page) partent ensemble : ils lisent la même table, et les séparer
 * en cascade doublerait l'attente sans rien gagner. L'accès au jeu (D11) est contrôlé avant tout
 * chargement — un compte non invité voit une page inexistante, comme le serveur le lui répond déjà.
 */
export function MesPartiesView() {
  const [refuse, setRefuse] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [stats, setStats] = useState<StatistiquesJoueur | null>(null);
  const [historique, setHistorique] = useState<HistoriqueParties | null>(null);
  const [page, setPage] = useState(0);
  const [resultat, setResultat] = useState("");
  const [deckChoisi, setDeckChoisi] = useState("");
  const [sansEntrainement, setSansEntrainement] = useState(false);

  useEffect(() => {
    let actif = true;
    getProfile()
      .then((profil) => {
        if (!actif) return;
        if (!profil.game_access) setRefuse(true);
      })
      .catch((cause) => {
        if (actif) setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
      });
    return () => {
      actif = false;
    };
  }, []);

  const filtres = useMemo<FiltresParties>(
    () => ({
      resultat: resultat || undefined,
      deck_id: deckChoisi || undefined,
      entrainement: sansEntrainement ? false : undefined,
    }),
    [resultat, deckChoisi, sansEntrainement]
  );

  const recharger = useCallback(async () => {
    try {
      const [agregats, liste] = await Promise.all([
        getMesStatistiques({ deck_id: filtres.deck_id, entrainement: filtres.entrainement }),
        listMesParties({ ...filtres, limite: PAR_PAGE, offset: page * PAR_PAGE }),
      ]);
      setStats(agregats);
      setHistorique(liste);
      setErreur(null);
    } catch (cause) {
      // Jamais un écran vide muet : on dit que le chargement a échoué plutôt que de laisser
      // croire « aucune partie », ce qui serait un repli masquant une panne.
      setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
    }
  }, [filtres, page]);

  useEffect(() => {
    if (refuse) return;
    void recharger();
  }, [refuse, recharger]);

  if (refuse) {
    notFound();
  }

  const totaux = stats?.totaux;
  const parties = historique?.parties ?? [];
  const total = historique?.total ?? 0;
  const dernierePage = Math.max(0, Math.ceil(total / PAR_PAGE) - 1);

  return (
    <section className="mx-auto w-full max-w-4xl px-4 py-8">
      <header className="mb-6">
        <h1 className="font-heading text-xl font-bold uppercase tracking-[0.08em] text-gold">
          Mes parties
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ce que tes parties ont donné, deck par deck et adversaire par adversaire. Les
          entraînements contre le bot sont listés mais n&apos;entrent dans aucun taux.
        </p>
      </header>

      {erreur && <FormNotice variant="error">{erreur}</FormNotice>}

      {totaux && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="col-span-2 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 sm:col-span-2">
            <TauxVictoire taux={totaux.taux} libelle="Taux de victoire" />
          </div>
          <Tuile
            libelle="Série en cours"
            valeur={`${totaux.serie_en_cours}`}
            precision={`record : ${totaux.meilleure_serie}`}
          />
          <Tuile
            libelle="Temps de jeu"
            valeur={libelleDuree(totaux.temps_jeu_s)}
            precision={
              totaux.parties_entrainement > 0
                ? `+ ${libelleDuree(totaux.temps_jeu_entrainement_s)} d'entraînement`
                : null
            }
          />
        </div>
      )}

      {stats && stats.par_deck.length > 0 && (
        <div className="mt-8">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-[0.08em]">
            Par deck
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {stats.par_deck.map((deck) => (
              <LigneDeck key={deck.deck_id ?? "supprime"} deck={deck} />
            ))}
          </ul>
        </div>
      )}

      {stats && stats.par_adversaire.length > 0 && (
        <div className="mt-8">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-[0.08em]">
            Par adversaire
          </h2>
          <ul className="mt-3 flex flex-col gap-2">
            {stats.par_adversaire.map((adversaire) => (
              <li
                key={adversaire.user_id ?? "bot"}
                data-testid="adversaire"
                className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3"
              >
                <span className="text-sm">{nomAdversaire(adversaire)}</span>
                <TauxVictoire taux={adversaire.taux} libelle="Mes victoires" />
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-[0.08em]">
            Historique {total > 0 && <span data-testid="total">({total})</span>}
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-xs text-muted-foreground" htmlFor="filtre-resultat">
              Résultat
              <select
                id="filtre-resultat"
                value={resultat}
                onChange={(event) => {
                  setPage(0);
                  setResultat(event.target.value);
                }}
                className="ml-2 rounded-lg border border-[rgba(157,0,255,0.3)] bg-background px-2 py-1 text-sm text-foreground"
              >
                <option value="">Tous</option>
                {Object.entries(RESULTATS).map(([code, libelle]) => (
                  <option key={code} value={code}>
                    {libelle}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-muted-foreground" htmlFor="filtre-deck">
              Deck
              <select
                id="filtre-deck"
                value={deckChoisi}
                onChange={(event) => {
                  setPage(0);
                  setDeckChoisi(event.target.value);
                }}
                className="ml-2 rounded-lg border border-[rgba(157,0,255,0.3)] bg-background px-2 py-1 text-sm text-foreground"
              >
                <option value="">Tous</option>
                {(stats?.par_deck ?? [])
                  .filter((deck) => deck.deck_id !== null)
                  .map((deck) => (
                    <option key={deck.deck_id} value={deck.deck_id ?? ""}>
                      {nomDeck(deck)}
                    </option>
                  ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={sansEntrainement}
                onChange={(event) => {
                  setPage(0);
                  setSansEntrainement(event.target.checked);
                }}
                className="h-4 w-4 accent-[#FFD700]"
              />
              Masquer l&apos;entraînement
            </label>
          </div>
        </div>

        {parties.length === 0 ? (
          <EmptyState
            title="Aucune partie pour l'instant"
            description="Tes parties finies apparaîtront ici, avec leur replay."
          />
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {parties.map((partie) => (
              <LignePartie key={partie.game_id} partie={partie} />
            ))}
          </ul>
        )}

        {total > PAR_PAGE && (
          <div className="mt-4 flex items-center justify-between gap-3">
            <Button
              type="button"
              variant="outline"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Plus récentes
            </Button>
            <span data-testid="page" className="text-xs text-muted-foreground">
              Page {page + 1} sur {dernierePage + 1}
            </span>
            <Button
              type="button"
              variant="outline"
              disabled={page >= dernierePage}
              onClick={() => setPage((p) => Math.min(dernierePage, p + 1))}
            >
              Plus anciennes
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
