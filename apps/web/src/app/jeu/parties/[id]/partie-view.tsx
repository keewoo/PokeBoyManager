"use client";

import { notFound } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { useFileAnimations } from "@/components/game/animation-layer";
import { EmoteBar } from "@/components/game/emote-bar";
import { FenetreDecision } from "@/components/game/fenetre-decision";
import { FinPartie } from "@/components/game/fin-partie";
import { GameBoard } from "@/components/game/game-board";
import { JournalPanel } from "@/components/game/journal-panel";
import { ApiError } from "@/lib/api/client";
import { getGameState, playAction } from "@/lib/api/games";
import { CanalPartie, type Coup, type EtatConnexion } from "@/lib/game/realtime";
import type { CodeEmote, EmoteRecue } from "@/lib/game/emotes";
import { ACTION_REPONDRE_DEMANDE } from "@/lib/game/decision";
import { agisseurDepuisEvenements } from "@/lib/game/indicateurs";
import { estPremierePartie, marquerGuideVu } from "@/lib/game/guide";
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
 *
 * La **fin de partie** (lot `j-partie-fin-ui`) se déclenche sur `vue.terminee` — décidé par le
 * serveur, jamais déduit ici. L'écran de fin est posé **hors du flux** (`fixed`) : la page du
 * plateau ne tolère aucun défilement, et il va chercher lui-même ses chiffres
 * (`GET /games/{id}/recapitulatif`, recalculés depuis le journal) plutôt que de compter les
 * coups accumulés ici — un F5 rejoue toute la partie, donc un compteur local doublerait.
 *
 * Les **emotes** (lot `j-echanges-emotes`, DJ10) sont le seul message qui n'est **pas** un coup :
 * elles ne portent aucun numéro, n'entrent ni dans `coups` ni dans le journal, et on n'en garde
 * qu'**une** — la dernière reçue, le temps de sa bulle. Rien n'en survit à la partie, pas même un
 * compteur. L'envoi passe par le canal (`envoyerEmote`) et par lui seul : aucune route HTTP, donc
 * aucune file d'attente, donc rien à stocker.
 *
 * Les **animations** (lot `j-anim-socle`) se nourrissent de ces mêmes coups, et de rien d'autre :
 * les effets suivent les événements, jamais l'inverse. La file (`useFileAnimations`) n'est branchée
 * sur aucun état du plateau — ni `vue`, ni `numeroRef` — et jouer un coup la **jette** avant même
 * de soumettre. Une animation ne peut donc, à aucun instant, retarder une action légale ni montrer
 * un état que le serveur n'a pas décidé. Un F5 arrive avec toute la partie d'un bloc : la file la
 * résume (rattrapage) au lieu de rejouer cent coups un par un.
 */
export function PartieView({ gameId }: { gameId: string }) {
  const [denied, setDenied] = useState(false);
  // L'identifiant du **compte** connecté : l'écran de fin compare le vainqueur à celui-là, et
  // jamais à l'identifiant moteur du joueur (deux espaces de noms distincts).
  const [moiUserId, setMoiUserId] = useState<string | null>(null);
  const [introuvable, setIntrouvable] = useState(false);
  const [accessReady, setAccessReady] = useState(false);
  const [vue, setVue] = useState<VuePartie | null>(null);
  // Première partie ? C'est ici qu'on tranche, une fois, au montage — pas dans le tiroir d'aide :
  // `localStorage` n'existe pas au rendu serveur, et la réponse ne doit pas changer en cours de
  // partie (le guide se refermerait sous les doigts du joueur). On note aussitôt que le guide a
  // été vu : la partie suivante ne l'ouvrira plus d'elle-même (lot `j-plateau-aide`).
  const [premierePartie] = useState(() => {
    const stockage = typeof window === "undefined" ? null : window.localStorage;
    const premiere = estPremierePartie(stockage);
    if (premiere) marquerGuideVu(stockage);
    return premiere;
  });
  const [etatConnexion, setEtatConnexion] = useState<EtatConnexion>("connexion");
  // Le Pokémon qui vient d'agir, mis en évidence par un halo (lot `j-plateau-etat-visuel`).
  const [agisseur, setAgisseur] = useState<string | null>(null);
  // Le Pokémon désigné par la ligne de journal survolée : mis en évidence le temps du survol.
  const [surligne, setSurligne] = useState<string | null>(null);
  // Les coups diffusés, dans l'ordre, pour alimenter le journal de partie.
  const [coups, setCoups] = useState<Coup[]>([]);
  // La dernière emote reçue (lot `j-echanges-emotes`) : **une seule**, jamais un historique. Rien
  // d'une emote ne survit à la partie, pas même ici. `cle` rend la référence nouvelle à chaque
  // réception, pour que deux emotes identiques de suite rallument bien la bulle.
  const [emoteRecue, setEmoteRecue] = useState<(EmoteRecue & { cle: number }) | null>(null);
  const [emoteRefus, setEmoteRefus] = useState<{ code: string; message: string } | null>(null);
  const emoteCle = useRef(0);
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
        setMoiUserId(profile.id);
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
      onEmote: (emote) => {
        if (!active) return;
        emoteCle.current += 1;
        setEmoteRecue({ ...emote, cle: emoteCle.current });
      },
      onEmoteRefusee: (code, message) => {
        if (active) setEmoteRefus({ code, message });
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
  // La file d'animations, alimentée par les coups diffusés et par eux seuls.
  const anim = useFileAnimations({ coups, pour: vue?.pour ?? "", cle: gameId });
  const viderAnimations = anim.vider;

  const onJouer = useCallback(
    async (action: VueActionLegale) => {
      // Le joueur agit : on jette ce qui restait à animer. L'écran ne se met jamais en travers.
      viderAnimations();
      const rep = await playAction(gameId, {
        type: action.type,
        params: action.params,
        numero_attendu: numeroRef.current,
      });
      setVue(rep.vue);
      numeroRef.current = typeof rep.numero === "number" ? rep.numero : numeroRef.current + 1;
    },
    [gameId, viderAnimations],
  );

  /**
   * Répond à une demande de décision (lot `j-plateau-decisions`) : soumet, par la **même** route
   * que tout coup, l'action `repondre_demande` portant l'identifiant de la demande et les options
   * retenues (liste vide = abandon d'un effet facultatif). Le serveur fait autorité — il rejoue la
   * réponse, reprend la résolution suspendue, et renvoie la vue projetée (demande suivante ou
   * disparue) ; un refus (`ApiError` 422) **remonte** à la fenêtre, qui en affiche la raison du moteur.
   */
  const onRepondre = useCallback(
    async (demandeId: string, choix: string[]) => {
      viderAnimations();
      const rep = await playAction(gameId, {
        type: ACTION_REPONDRE_DEMANDE,
        params: { demande_id: demandeId, choix },
        numero_attendu: numeroRef.current,
      });
      setVue(rep.vue);
      numeroRef.current = typeof rep.numero === "number" ? rep.numero : numeroRef.current + 1;
    },
    [gameId, viderAnimations],
  );

  /**
   * Envoie une emote prédéfinie par le canal temps réel (lot `j-echanges-emotes`). Renvoie `false`
   * si le canal direct n'est pas ouvert — la palette le dit alors au joueur. Aucun texte ne passe
   * par ici : le type `CodeEmote` est une union fermée, et le serveur revalide le code.
   */
  const onEnvoyerEmote = useCallback((code: CodeEmote) => {
    return canal.current?.envoyerEmote(code) ?? false;
  }, []);

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
            animation={anim.animation}
            animationDuree={anim.duree}
            animationsEnAttente={anim.enAttente}
            onSauterAnimation={anim.sauter}
            onBasculerAccelere={anim.reduit ? undefined : anim.basculerAccelere}
            animationAcceleree={anim.mode === "accelere"}
            premierePartie={premierePartie}
          />
          <JournalPanel lignes={lignes} onSurvol={setSurligne} />
          {/* Emotes (lot `j-echanges-emotes`, DJ10) : palette fermée, hors flux, désactivable. */}
          <EmoteBar
            onEnvoyer={onEnvoyerEmote}
            recue={emoteRecue}
            refus={emoteRefus}
            direct={etatConnexion === "direct"}
          />
          <FenetreDecision vue={vue} onRepondre={onRepondre} />
          {vue.terminee && moiUserId && (
            <FinPartie
              gameId={gameId}
              moiUserId={moiUserId}
              raisonFinVue={vue.raison_fin ?? null}
            />
          )}
        </>
      )}
    </div>
  );
}
