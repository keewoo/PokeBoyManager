"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/api/client";
import {
  RENDU_OFFICIELLE,
  RENDU_PHOTO,
  getDeckRendu,
  type ApercuDeckRendu,
} from "@/lib/api/rendu";

/**
 * « Avec quelles cartes ce deck se joue » — le panneau de rendu du constructeur de deck (lot
 * `j-rendu-carte`, décision DJ5).
 *
 * Il fait deux choses, et la seconde est la raison d'être du panneau :
 *
 * 1. il règle le rendu **de ce deck** (ou le laisse suivre le réglage global du compte) ;
 * 2. il **dit** quelles cartes ne se joueront pas avec leur photo, et pourquoi — « photo trop
 *    sombre », « carte coupée sur la photo », « aucune photo de cette carte ». Sans ça, le repli
 *    serait muet : le joueur croirait que ses photos n'ont pas été prises en compte, alors qu'elles
 *    l'ont été et jugées illisibles à la taille d'un plateau.
 *
 * Charger ce panneau **prépare** côté serveur les variantes de jeu manquantes du deck : c'est le
 * moment « à l'avance » du lot, pour qu'aucune image ne soit fabriquée pendant une partie.
 */
export function DeckRenduPanel({
  deckId,
  renduDeck,
  onChangerRendu,
  enCours,
}: {
  deckId: string;
  renduDeck: string | null;
  onChangerRendu: (rendu: string) => void;
  enCours?: boolean;
}) {
  const [apercu, setApercu] = useState<ApercuDeckRendu | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    setErreur(null);
    getDeckRendu(deckId)
      .then((a) => {
        if (actif) setApercu(a);
      })
      .catch((cause) => {
        // Un aperçu qui ne charge pas se dit : afficher « tout va bien » serait un repli
        // silencieux, et le joueur découvrirait le problème en pleine partie.
        if (actif) {
          setApercu(null);
          setErreur(cause instanceof ApiError ? cause.message : "Aperçu indisponible.");
        }
      });
    return () => {
      actif = false;
    };
    // `renduDeck` en dépendance : changer le réglage change l'aperçu (tout passe en officielle).
  }, [deckId, renduDeck]);

  return (
    <section
      data-testid="deck-rendu"
      className="mt-6 rounded-2xl border border-[rgba(157,0,255,0.3)] p-4"
      aria-labelledby="titre-deck-rendu"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="titre-deck-rendu" className="font-heading text-sm font-bold uppercase tracking-[0.13em]">
          Mes cartes en jeu
        </h2>
        <select
          aria-label="Rendu des cartes de ce deck"
          data-testid="deck-rendu-choix"
          className="flex h-10 rounded-full border border-input bg-card px-4 text-sm text-foreground"
          value={renduDeck ?? ""}
          disabled={enCours}
          onChange={(e) => onChangerRendu(e.target.value)}
        >
          <option value="">Suivre mon réglage par défaut</option>
          <option value={RENDU_PHOTO}>Mes photos</option>
          <option value={RENDU_OFFICIELLE}>Images officielles</option>
        </select>
      </div>

      {erreur && (
        <p role="alert" className="mt-3 text-sm text-danger-foreground">
          {erreur}
        </p>
      )}

      {apercu && (
        <>
          <p className="mt-3 text-sm text-muted-foreground">
            {apercu.rendu_effectif === RENDU_PHOTO ? (
              <>
                <Badge variant="success">{apercu.nb_photos} avec ta photo</Badge>{" "}
                {apercu.nb_officielles > 0 && (
                  <Badge variant="outline">{apercu.nb_officielles} en image officielle</Badge>
                )}
              </>
            ) : (
              <>Ce deck se joue avec les images officielles du catalogue.</>
            )}
          </p>

          {apercu.rendu_effectif === RENDU_PHOTO && apercu.cartes.length > 0 && (
            <>
              <p className="mt-3 text-xs text-muted-foreground">
                Ces cartes se joueront avec l&apos;image officielle — la partie n&apos;attend jamais
                pour une photo :
              </p>
              <ul data-testid="deck-rendu-replis" className="mt-2 space-y-1 text-xs">
                {apercu.cartes.map((carte) => (
                  <li key={carte.card_id} className="flex flex-wrap gap-x-2">
                    <span className="font-semibold">{carte.nom}</span>
                    <span className="text-muted-foreground">{carte.raison ?? "image officielle"}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}
