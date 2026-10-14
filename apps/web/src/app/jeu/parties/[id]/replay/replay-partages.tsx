"use client";

import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import {
  type PartageReplay,
  fermerPartageReplay,
  listReplayPartages,
  ouvrirPartageReplay,
} from "@/lib/api/games";

/**
 * Partage d'un replay (lot `j-replay`) : à qui ce replay est ouvert, et comment l'ouvrir ou le fermer.
 *
 * **Réservé aux deux joueurs** — c'est le serveur qui le décide (404 pour tout autre compte, y
 * compris pour un spectateur autorisé : regarder n'est pas administrer). Ce panneau n'essaie donc
 * pas de devenir qui a le droit : il demande la liste, et **se retire** si le serveur répond 404.
 *
 * Ce qu'on partage est un **droit**, pas un lien porteur : le lien du replay est l'URL ordinaire de
 * cette page, et un compte non autorisé n'en fait rien. C'est pour ça que l'écran parle de « compte »
 * (par son pseudo) et jamais de « lien à copier » — il n'y a pas de secret à copier.
 */
export function ReplayPartages({ gameId }: { gameId: string }) {
  const [visible, setVisible] = useState(true);
  const [partages, setPartages] = useState<PartageReplay[]>([]);
  const [pseudo, setPseudo] = useState("");
  const [occupe, setOccupe] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const charger = useCallback(async () => {
    try {
      setPartages(await listReplayPartages(gameId));
    } catch (err) {
      // 404 : ce compte ne gère pas les partages de cette partie. Le panneau disparaît — il
      // n'avait rien à proposer.
      if (err instanceof ApiError && err.status === 404) setVisible(false);
      else setErreur("Chargement des partages impossible. Réessaie dans un instant.");
    }
  }, [gameId]);

  useEffect(() => {
    void charger();
  }, [charger]);

  const ouvrir = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const cible = pseudo.trim();
      if (!cible || occupe) return;
      setOccupe(true);
      setErreur(null);
      try {
        await ouvrirPartageReplay(gameId, cible);
        setPseudo("");
        await charger();
      } catch (err) {
        // Le serveur fait autorité : on affiche SA raison (pseudo inconnu, joueur de la partie),
        // jamais un texte inventé.
        setErreur(
          err instanceof ApiError ? err.message : "Partage impossible. Réessaie dans un instant.",
        );
      } finally {
        setOccupe(false);
      }
    },
    [charger, gameId, occupe, pseudo],
  );

  const fermer = useCallback(
    async (userId: string) => {
      setOccupe(true);
      setErreur(null);
      try {
        await fermerPartageReplay(gameId, userId);
        await charger();
      } catch (err) {
        setErreur(
          err instanceof ApiError ? err.message : "Retrait impossible. Réessaie dans un instant.",
        );
      } finally {
        setOccupe(false);
      }
    },
    [charger, gameId],
  );

  if (!visible) return null;

  return (
    <section data-testid="replay-partages" aria-label="Partage du replay" className="space-y-2">
      <h2 className="font-heading text-sm font-bold text-gold">Partager ce replay</h2>
      {erreur && <FormNotice variant="error">{erreur}</FormNotice>}

      <form onSubmit={ouvrir} className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs">
          <span className="sr-only">Pseudo du joueur invité</span>
          <input
            type="text"
            value={pseudo}
            onChange={(e) => setPseudo(e.target.value)}
            placeholder="Pseudo du joueur"
            aria-label="Pseudo du joueur invité"
            className="rounded-lg border border-[rgba(157,0,255,0.45)] bg-transparent px-2 py-1"
          />
        </label>
        <button
          type="submit"
          disabled={occupe || !pseudo.trim()}
          className="rounded-lg border border-[rgba(157,0,255,0.45)] px-2 py-1 text-xs disabled:opacity-40"
        >
          Ouvrir le replay
        </button>
      </form>

      {partages.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Ce replay n&apos;est ouvert qu&apos;aux deux joueurs.
        </p>
      ) : (
        <ul className="space-y-1">
          {partages.map((p) => (
            <li key={p.user_id} data-testid="replay-partage" className="flex items-center gap-2 text-xs">
              <span>{p.pseudo ?? "Compte sans pseudo"}</span>
              <button
                type="button"
                onClick={() => void fermer(p.user_id)}
                disabled={occupe}
                aria-label={`Retirer l'accès de ${p.pseudo ?? "ce compte"}`}
                className="rounded-lg border border-[rgba(226,80,59,0.45)] px-2 py-0.5 disabled:opacity-40"
              >
                Retirer
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
