"use client";

import { notFound } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { GameBoard } from "@/components/game/game-board";
import { JournalPanel } from "@/components/game/journal-panel";
import { ApiError } from "@/lib/api/client";
import { getGameState, playAction } from "@/lib/api/games";
import { CanalPartie, type Coup, type EtatConnexion } from "@/lib/game/realtime";
import { agisseurDepuisEvenements } from "@/lib/game/indicateurs";
import { construireJournal } from "@/lib/game/journal";
import type { VueActionLegale, VuePartie } from "@/lib/game/plateau";
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
 * plateau ne rejoue aucune règle — il affiche ce que le serveur lui donne, y compris les coups
 * jouables (`actions_legales`). **Jouer un coup** (lot `j-plateau-interactions`) passe par `onJouer` :
 * il soumet au serveur avec le `numero` d'action courant (idempotence), puis la vue et le numéro
 * suivent la réponse — un coup refusé remonte sa raison (le message du moteur) au plateau.
 *
 * Le **journal de partie** (lot `j-plateau-journal`) est tenu ici : chaque coup diffusé (`onCoup`)
 * est accumulé, dédupliqué par numéro et traduit en fil français (`construireJournal`). Comme un F5
 * rouvre le canal depuis le coup 0, le journal se reconstruit entièrement — tout est rejouable.
 */
export function PartieView({ gameId }: { gameId: string }) {
  const [denied, setDenied] = useState(false);
  const [introuvable, setIntrouvable] = useState(false);
  const [accessReady, setAccessReady] = useState(false);
  const [vue, setVue] = useState<VuePartie | null>(null);
  const [etatConnexion, setEtatConnexion] = useState<EtatConnexion>("connexion");
  // Le Pokémon qui vient d'agir, mis en évidence par un halo (lot `j-plateau-etat-visuel`).
  const [agisseur, setAgisseur] = useState<string | null>(null);
  // Le Pokémon désigné par la ligne de journal survolée : mis en évidence le temps du survol.
  const [surligne, setSurligne] = useState<string | null>(null);
  // Les coups diffusés, dans l'ordre, pour alimenter le journal de partie.
  const [coups, setCoups] = useState<Coup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const canal = useRef<CanalPartie | null>(null);
  // Numéro d'action courant (prochain attendu) : clé d'idempotence pour soumettre un coup. Tenu en
  // ref pour que `onJouer` lise toujours la dernière valeur sans se recréer à chaque coup.
  const numeroRef = useRef(0);

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
    // Nouveau canal (ou changement de partie) : le journal repart de zéro — il se reconstruira depuis
    // le coup 0 (la resync initiale rejoue tout). Pas d'accumulation d'une partie précédente.
    setCoups([]);

    getGameState(gameId)
      .then((etat) => {
        if (!active) return;
        setVue(etat.vue);
        numeroRef.current = etat.numero ?? 0;
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
      onVue: (v, numero) => {
        if (!active) return;
        setVue(v as VuePartie);
        numeroRef.current = numero;
      },
      onCoup: (coup) => {
        if (!active) return;
        // Journal : on garde le coup, dédupliqué par numéro et rangé dans l'ordre. Le canal ne
        // rediffuse jamais un numéro déjà appliqué, mais on se protège d'une resync qui recouvre.
        setCoups((prev) => {
          const idx = prev.findIndex((c0) => c0.numero === coup.numero);
          const base = idx >= 0 ? prev.map((c0, i) => (i === idx ? coup : c0)) : [...prev, coup];
          return base.sort((a, b) => a.numero - b.numero);
        });
        // On relève en plus QUI vient d'agir pour le mettre en évidence (halo). Les animations fines
        // des coups sont le lot aval `j-anim-socle`.
        const acteur = agisseurDepuisEvenements(coup.evenements);
        if (acteur) setAgisseur(acteur);
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

  /**
   * Joue un coup : soumet au serveur l'action exacte que le moteur a déclarée, avec le numéro courant
   * (idempotence). En retour, la vue projetée et le numéro suivant priment. Un refus (`ApiError` 422)
   * **remonte** au plateau, qui en affiche la raison du moteur ; on ne touche alors ni la vue ni le
   * numéro (l'état n'a pas bougé côté serveur). L'action du moteur porte déjà tout ce qu'il faut
   * journaliser ; la cible choisie ne sert qu'à illuminer côté écran (lot aval côté cartes).
   */
  const onJouer = useCallback(
    async (action: VueActionLegale) => {
      const rep = await playAction(gameId, {
        type: action.type,
        params: action.params,
        numero_attendu: numeroRef.current,
      });
      setVue(rep.vue);
      numeroRef.current = typeof rep.numero === "number" ? rep.numero : numeroRef.current + 1;
    },
    [gameId],
  );

  // Le fil du journal, reconstruit quand un coup arrive ou que la vue change de destinataire.
  const lignes = useMemo(
    () => (vue ? construireJournal(coups, vue.pour) : []),
    [coups, vue],
  );

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
      {vue && (
        <>
          <GameBoard
            vue={vue}
            etatConnexion={etatConnexion}
            agisseur={agisseur}
            surligne={surligne}
            onJouer={onJouer}
          />
          <JournalPanel lignes={lignes} onSurvol={setSurligne} />
        </>
      )}
    </div>
  );
}
