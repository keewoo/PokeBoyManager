"use client";

import { notFound } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { GameBoard } from "@/components/game/game-board";
import { ApiError } from "@/lib/api/client";
import { getGameState } from "@/lib/api/games";
import { CanalPartie, type EtatConnexion } from "@/lib/game/realtime";
import type { VuePartie } from "@/lib/game/plateau";
import { getProfile } from "@/lib/api/profile";

/**
 * Le plateau d'une partie (lot `j-plateau-layout`), à `/jeu/parties/{id}`.
 *
 * Trois choses, dans l'ordre : il **gate l'accès** (droit au jeu D11 + participation à cette partie,
 * tous deux décidés par le serveur — un refus devient une page inexistante, jamais une porte vers un
 * 404) ; il **charge la vue autoritaire** initiale ; puis il **branche le canal temps réel**
 * (`CanalPartie`, lot `j-temps-reel`) qui applique les coups par numéro, se resynchronise après un
 * trou et replie en interrogation périodique quand le WebSocket est impossible.
 *
 * Le serveur fait autorité : chaque resynchronisation porte la vue complète, qui prime toujours. Le
 * plateau ne rejoue aucune règle — il affiche ce que le serveur lui donne. La reprise après un F5 et
 * le redessin après une rotation d'écran tiennent à cela : l'état n'est jamais reconstruit côté
 * écran, il est redemandé.
 */
export function PartieView({ gameId }: { gameId: string }) {
  const [denied, setDenied] = useState(false);
  const [introuvable, setIntrouvable] = useState(false);
  const [accessReady, setAccessReady] = useState(false);
  const [vue, setVue] = useState<VuePartie | null>(null);
  const [etatConnexion, setEtatConnexion] = useState<EtatConnexion>("connexion");
  const [error, setError] = useState<string | null>(null);
  const canal = useRef<CanalPartie | null>(null);

  // Étape 1 — autorité d'accès : droit au jeu (D11). Faux → page inexistante.
  useEffect(() => {
    let active = true;
    getProfile()
      .then((profile) => {
        if (!active) return;
        if (!profile.game_access) setDenied(true);
      })
      .catch(() => {
        // Une panne réseau n'est pas un refus : on montre un message plutôt que de masquer la partie.
        if (active) setError("Chargement de la partie impossible. Réessaie dans un instant.");
      })
      .finally(() => {
        if (active) setAccessReady(true);
      });
    return () => {
      active = false;
    };
  }, []);

  // Étape 2 — vue initiale + canal temps réel, une fois l'accès confirmé.
  useEffect(() => {
    if (!accessReady || denied) return;
    let active = true;

    getGameState(gameId)
      .then((etat) => {
        if (active) setVue(etat.vue);
      })
      .catch((err) => {
        if (!active) return;
        // 404 : la partie n'existe pas pour ce joueur → page inexistante (pas de fuite).
        if (err instanceof ApiError && err.status === 404) setIntrouvable(true);
        else setError("Chargement de la partie impossible. Réessaie dans un instant.");
      });

    // Le canal applique ensuite les coups et resynchronise ; sa vue (serveur autoritaire) prime.
    const c = new CanalPartie({
      gameId,
      depuis: 0,
      onVue: (v) => {
        if (active) setVue(v as VuePartie);
      },
      onCoup: () => {
        // Les coups animés (dégâts, déplacements) sont le lot aval `j-plateau-etat-visuel` : ici, la
        // resynchronisation portée par la vue suffit à garder le plateau à jour.
      },
      onEtat: (e) => {
        if (active) setEtatConnexion(e);
      },
    });
    canal.current = c;
    c.demarrer();

    return () => {
      active = false;
      c.arreter();
      canal.current = null;
    };
  }, [accessReady, denied, gameId]);

  if (denied || introuvable) {
    notFound();
    return null;
  }

  if (!accessReady || (!vue && !error)) {
    return <p className="text-sm text-muted-foreground">Chargement de la partie…</p>;
  }

  return (
    <div className="space-y-3">
      {error && <FormNotice variant="error">{error}</FormNotice>}
      {vue && <GameBoard vue={vue} etatConnexion={etatConnexion} />}
    </div>
  );
}
