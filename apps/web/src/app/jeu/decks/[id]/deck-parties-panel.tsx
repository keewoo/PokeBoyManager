"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  getMesStatistiques,
  libelleDuree,
  libelleTaux,
  phraseNonSignificatif,
  type StatsDeck,
} from "@/lib/api/stats-joueur";

// Ce que ce deck a donné en partie, sur sa propre fiche (lot `j-stats-joueur`).
//
// Appelle `/jeu/mes-statistiques?deck_id=…` — la **même** route que la page « Mes parties », avec
// un filtre. Avoir son propre calcul ici aurait fini par afficher un taux différent de celui du
// tableau général sur le même historique, et c'est exactement ce qu'on reproche à un chiffre
// (vérifié par `test_le_filtre_par_deck_donne_le_meme_chiffre_que_le_tableau`).
//
// Le bloc ne s'affiche pas tant que le deck n'a aucune partie : un panneau « 0 % de victoires »
// sur un deck jamais joué se lirait comme un mauvais deck.

/** Bilan en partie du deck affiché, ou rien quand il n'a pas encore été joué. */
export function DeckPartiesPanel({ deckId }: { deckId: string }) {
  const [deck, setDeck] = useState<StatsDeck | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    getMesStatistiques({ deck_id: deckId })
      .then((stats) => {
        if (!actif) return;
        setDeck(stats.par_deck.find((ligne) => ligne.deck_id === deckId) ?? null);
        setErreur(null);
      })
      .catch((cause) => {
        if (!actif) return;
        // Un 404 ici n'est pas une panne : c'est D11 (ce compte n'a pas accès au jeu, donc il n'a
        // aucune partie à montrer). Le panneau disparaît. Toute AUTRE erreur se dit — un bloc
        // vide sur une vraie panne ferait croire à un deck jamais joué.
        if (cause instanceof ApiError && cause.status === 404) return;
        setErreur(cause instanceof ApiError ? cause.message : "Statistiques indisponibles.");
      });
    return () => {
      actif = false;
    };
  }, [deckId]);

  if (erreur) {
    return (
      <p data-testid="deck-parties-erreur" className="text-xs text-muted-foreground">
        {erreur}
      </p>
    );
  }
  if (!deck || deck.taux.parties === 0) return null;

  const avertissement = phraseNonSignificatif(deck.taux);
  return (
    <section
      data-testid="deck-parties"
      className="rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3"
    >
      <h3 className="font-heading text-sm font-semibold uppercase tracking-[0.08em]">
        Ce deck en partie
      </h3>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <p className="text-2xl font-bold">{libelleTaux(deck.taux)}</p>
        <p className="text-xs text-muted-foreground">
          {deck.taux.parties} partie{deck.taux.parties > 1 ? "s" : ""} · {deck.taux.victoires} V ·{" "}
          {deck.taux.defaites} D · {deck.taux.egalites} N · durée moyenne{" "}
          {libelleDuree(deck.duree_moyenne_s)}
        </p>
      </div>
      {avertissement ? (
        <p data-testid="deck-parties-reserve" className="mt-1 text-xs text-[#C77DFF]">
          {avertissement}
        </p>
      ) : null}

      {deck.adversaires.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 border-t border-[rgba(157,0,255,0.2)] pt-3">
          {deck.adversaires.map((adversaire) => (
            <li
              key={adversaire.user_id ?? "bot"}
              className="flex flex-wrap items-baseline justify-between gap-2 text-sm"
            >
              <span>{adversaire.bot ? "Entraînement (bot)" : (adversaire.pseudo ?? "?")}</span>
              <span className="text-muted-foreground">
                {libelleTaux(adversaire.taux)} sur {adversaire.taux.parties}
                {adversaire.taux.significatif ? "" : " (trop peu pour conclure)"}
              </span>
            </li>
          ))}
        </ul>
      )}

      <Link href="/jeu/parties" className="mt-3 inline-block text-sm text-[#C77DFF] underline">
        Voir toutes mes parties
      </Link>
    </section>
  );
}
