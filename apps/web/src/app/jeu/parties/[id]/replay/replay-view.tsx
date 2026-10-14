"use client";

import { notFound } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { GameBoard } from "@/components/game/game-board";
import { JournalPanel } from "@/components/game/journal-panel";
import { ApiError } from "@/lib/api/client";
import {
  REPLAY_VUE_COMPLETE,
  REPLAY_VUE_MOI,
  type ReplayEtape,
  type ReplayPage,
  getReplay,
} from "@/lib/api/games";
import { getProfile } from "@/lib/api/profile";
import { construireJournal } from "@/lib/game/journal";
import type { VuePartie } from "@/lib/game/plateau";
import {
  VITESSES,
  borner,
  coupsJusqua,
  delaiMs,
  destinatairesDe,
  estComplet,
  fusionnerRangs,
  nomDu,
  rangA,
  rangsManquants,
} from "@/lib/game/replay";

import { ReplayPartages } from "./replay-partages";

/** Rangs demandés par page : assez pour que la navigation soit fluide, assez peu pour arriver vite. */
const PAR_PAGE = 50;

/**
 * Un message d'information (ni erreur, ni succès) : « la partie n'est pas finie », « tu regardes en
 * vue complète ». `FormNotice` ne connaît que l'erreur et le succès, et on ne repeint pas un
 * composant partagé au passage d'un lot (`apps/web/CLAUDE.md`) — d'où cet encart local, avec le
 * `role="status"` qui le fait annoncer par un lecteur d'écran.
 */
function Avis({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      data-testid="replay-avis"
      className="rounded-xl border border-[rgba(157,0,255,0.35)] bg-[rgba(20,27,92,0.6)] px-3 py-2 text-sm text-foreground"
    >
      {children}
    </p>
  );
}

/**
 * Le replay d'une partie finie (`/jeu/parties/{id}/replay`, lot `j-replay`).
 *
 * **Le serveur a déjà tout tranché** : il n'ouvre le replay qu'une fois la partie finie, il ne sert
 * que des états projetés (jamais la main adverse), et il n'ouvre la porte qu'aux deux joueurs et aux
 * comptes à qui l'un d'eux l'a ouverte. Cet écran ne refait aucun de ces contrôles — il les
 * **affiche** : un 404 devient une page inexistante, un 409 dit que la partie n'est pas finie.
 *
 * Ce qu'il fait, lui : charger les rangs page après page jusqu'au bout, puis **naviguer localement**
 * — avancer, reculer, se placer, lire en continu à la vitesse choisie. Aucun aller-retour par coup :
 * c'est ce qui rend le va-et-vient immédiat. Toute la logique de navigation est pure et testée à
 * part (`lib/game/replay.ts`) ; ici on tient l'état et on branche les boutons.
 *
 * Le plateau est en **lecture seule** : `GameBoard` sans `onJouer` ne montre aucune barre d'actions
 * et ne rend aucune cible saisissable — on regarde une partie finie, on n'y joue pas.
 */
export function ReplayView({ gameId }: { gameId: string }) {
  const [denied, setDenied] = useState(false);
  const [introuvable, setIntrouvable] = useState(false);
  const [accessReady, setAccessReady] = useState(false);
  const [entete, setEntete] = useState<ReplayPage | null>(null);
  const [rangs, setRangs] = useState<ReplayEtape[]>([]);
  const [rang, setRang] = useState(0);
  const [vue, setVue] = useState<string>(REPLAY_VUE_MOI);
  const [destinataire, setDestinataire] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [vitesse, setVitesse] = useState<number>(1);
  const [lecture, setLecture] = useState(false);
  const [avis, setAvis] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Les rangs déjà chargés, en ref : la boucle de chargement les lit sans se recréer à chaque page.
  const rangsRef = useRef<ReplayEtape[]>([]);

  // Étape 1 — droit d'accès au jeu (D11). Faux → page inexistante, comme le plateau.
  useEffect(() => {
    let actif = true;
    getProfile()
      .then((profil) => {
        if (actif && !profil.game_access) setDenied(true);
      })
      .catch(() => {
        if (actif) setError("Chargement du replay impossible. Réessaie dans un instant.");
      })
      .finally(() => {
        if (actif) setAccessReady(true);
      });
    return () => {
      actif = false;
    };
  }, []);

  // Étape 2 — charger les rangs, page après page, jusqu'à `complet`.
  useEffect(() => {
    if (!accessReady || denied) return;
    let actif = true;
    setRangs([]);
    rangsRef.current = [];
    setRang(0);
    setLecture(false);
    setEnCours(true);

    /** Demande la page qui commence à `depuis`, en traitant les refus du serveur sans les masquer. */
    async function page(depuis: number, vueDemandee: string): Promise<ReplayPage | null> {
      try {
        return await getReplay(gameId, { vue: vueDemandee, depuis, limite: PAR_PAGE });
      } catch (err) {
        if (!(err instanceof ApiError)) {
          setError("Chargement du replay impossible. Réessaie dans un instant.");
          return null;
        }
        if (err.status === 404) {
          setIntrouvable(true);
          return null;
        }
        if (err.status === 409) {
          // Partie encore en cours : le replay n'existe pas encore. On le dit — c'est une réponse,
          // pas une panne.
          setAvis(err.message);
          return null;
        }
        if (err.status === 422 && vueDemandee === REPLAY_VUE_MOI) {
          // Le compte regarde une partie qu'il n'a pas jouée (replay partagé) : il n'a pas de
          // « moi ». On passe en vue complète — et on l'ÉCRIT à l'écran : un basculement muet
          // laisserait croire qu'on regarde par les yeux d'un joueur alors que non.
          setAvis("Tu n'as pas joué cette partie : elle s'ouvre en vue complète.");
          setVue(REPLAY_VUE_COMPLETE);
          return page(depuis, REPLAY_VUE_COMPLETE);
        }
        setError(err.message);
        return null;
      }
    }

    (async () => {
      let depuis = 0;
      for (;;) {
        const recue = await page(depuis, vue);
        if (!actif || !recue) break;
        setEntete(recue);
        const fusion = fusionnerRangs(rangsRef.current, recue.etapes);
        rangsRef.current = fusion;
        setRangs(fusion);
        if (recue.complet || recue.etapes.length === 0) break;
        depuis = recue.depuis + recue.etapes.length;
      }
      if (actif) setEnCours(false);
    })();

    return () => {
      actif = false;
    };
  }, [accessReady, denied, gameId, vue]);

  // Les destinataires servis (un en `vue=moi`, deux en `vue=complete`) et celui qu'on regarde.
  const destinataires = useMemo(
    () => (entete ? destinatairesDe({ joueurs: entete.joueurs, etapes: rangs }) : []),
    [entete, rangs],
  );
  useEffect(() => {
    // On ne garde un destinataire choisi que s'il est encore servi (la vue a pu changer).
    const premier = destinataires[0];
    if (premier && (!destinataire || !destinataires.includes(destinataire))) {
      setDestinataire(premier);
    }
  }, [destinataires, destinataire]);

  const total = entete?.total ?? 0;
  const manquants = rangsManquants(rangs, total);
  const complet = estComplet(rangs, total);

  // Lecture en continu : un pas par `delaiMs(vitesse)`, qui s'arrête au dernier rang chargé.
  useEffect(() => {
    if (!lecture) return;
    const minuteur = setTimeout(() => {
      setRang((courant) => {
        const suivant = borner(courant + 1, rangsRef.current);
        if (suivant === courant) setLecture(false); // arrivé au bout de ce qu'on a
        return suivant;
      });
    }, delaiMs(vitesse));
    return () => clearTimeout(minuteur);
  }, [lecture, vitesse, rang, rangs]);

  const aller = useCallback((cible: number) => {
    setLecture(false);
    setRang(borner(cible, rangsRef.current));
  }, []);

  const etape = rangA(rangs, rang);
  const vuePlateau = (destinataire && etape ? etape.vues[destinataire] : null) as VuePartie | null;
  const lignes = useMemo(
    () => (destinataire ? construireJournal(coupsJusqua(rangs, rang, destinataire), destinataire) : []),
    [rangs, rang, destinataire],
  );

  if (denied || introuvable) {
    notFound();
    return null;
  }

  if (avis && !vuePlateau) {
    // Partie en cours (409) : rien à rejouer, et on dit pourquoi plutôt que d'afficher un vide.
    return <Avis>{avis}</Avis>;
  }

  if (!accessReady || (!vuePlateau && !error)) {
    return <p className="text-sm text-muted-foreground">Chargement du replay…</p>;
  }

  return (
    <div className="space-y-3">
      {error && <FormNotice variant="error">{error}</FormNotice>}
      {avis && <Avis>{avis}</Avis>}

      {vuePlateau && entete && (
        <>
          {/* Hors flux, en haut : la barre de navigation n'allonge pas la page du plateau — le
              journal occupe déjà le bas de l'écran (tiroir `fixed`). */}
          <div className="pointer-events-none fixed inset-x-0 top-0 z-30 flex justify-center px-2 pt-2">
            <section
              data-testid="replay-controles"
              aria-label="Navigation du replay"
              className="pointer-events-auto flex w-full max-w-3xl flex-wrap items-center gap-2 rounded-2xl border border-[rgba(157,0,255,0.35)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] px-3 py-2 text-foreground shadow-[0_8px_30px_-12px_rgba(0,0,0,0.8)]"
            >
              <button
                type="button"
                onClick={() => aller(rang - 1)}
                disabled={rang <= 0}
                aria-label="Coup précédent"
                className="rounded-lg border border-[rgba(157,0,255,0.45)] px-2 py-1 text-sm disabled:opacity-40"
              >
                ◀
              </button>
              <button
                type="button"
                data-testid="replay-lecture"
                onClick={() => setLecture((l) => !l)}
                aria-label={lecture ? "Mettre en pause" : "Lire la partie"}
                className="rounded-lg border border-[rgba(157,0,255,0.45)] px-2 py-1 text-sm"
              >
                {lecture ? "❚❚" : "▶"}
              </button>
              <button
                type="button"
                onClick={() => aller(rang + 1)}
                disabled={rang >= (rangs.at(-1)?.rang ?? 0)}
                aria-label="Coup suivant"
                className="rounded-lg border border-[rgba(157,0,255,0.45)] px-2 py-1 text-sm disabled:opacity-40"
              >
                ▶
              </button>

              <label className="flex flex-1 items-center gap-2 text-xs">
                <span className="sr-only">Position dans la partie</span>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, rangs.at(-1)?.rang ?? 0)}
                  value={rang}
                  onChange={(e) => aller(Number(e.target.value))}
                  className="w-full"
                  aria-label="Position dans la partie"
                />
                <span data-testid="replay-position" className="shrink-0 tabular-nums">
                  {rang} / {total}
                </span>
              </label>

              <label className="flex items-center gap-1 text-xs">
                <span className="sr-only">Vitesse de lecture</span>
                <select
                  value={vitesse}
                  onChange={(e) => setVitesse(Number(e.target.value))}
                  aria-label="Vitesse de lecture"
                  className="rounded-lg border border-[rgba(157,0,255,0.45)] bg-transparent px-1 py-1"
                >
                  {VITESSES.map((v) => (
                    <option key={v} value={v}>
                      ×{v}
                    </option>
                  ))}
                </select>
              </label>

              {/* Vue complète : on choisit par quels yeux regarder. Jamais une vue « sans joueur » —
                  le serveur n'en sert pas. */}
              {destinataires.length > 1 && (
                <label className="flex items-center gap-1 text-xs">
                  <span className="sr-only">Regarder par les yeux de</span>
                  <select
                    value={destinataire ?? ""}
                    onChange={(e) => setDestinataire(e.target.value)}
                    aria-label="Regarder par les yeux de"
                    className="rounded-lg border border-[rgba(157,0,255,0.45)] bg-transparent px-1 py-1"
                  >
                    {destinataires.map((jid) => (
                      <option key={jid} value={jid}>
                        {nomDu(entete, jid)}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              {/* Ce qui n'est pas encore chargé se DIT : sans ça, la fin du curseur passerait pour
                  la fin de la partie. */}
              {!complet && (
                <span data-testid="replay-incomplet" className="text-xs text-gold">
                  {enCours ? `Chargement… ${manquants} coup(s) restant(s)` : `${manquants} coup(s) non chargé(s)`}
                </span>
              )}
            </section>
          </div>

          <GameBoard vue={vuePlateau} />
          <JournalPanel lignes={lignes} />

          {/* Les partages ne s'affichent que pour les deux joueurs — le serveur répond 404 aux
              autres, et le panneau se retire de lui-même dans ce cas. */}
          <ReplayPartages gameId={gameId} />
        </>
      )}
    </div>
  );
}
