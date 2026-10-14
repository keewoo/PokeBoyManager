"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";
import {
  RENDU_OFFICIELLE,
  RENDU_PHOTO,
  getRenduSettings,
  libelleRendu,
  updateRenduSettings,
  type ReglagesRendu,
} from "@/lib/api/rendu";

/**
 * Écran « Mes cartes en jeu » (`/jeu/rendu`) : avec quelles images je joue, et ce que
 * l'adversaire en voit (lot `j-rendu-carte`, décision DJ5).
 *
 * Un compte sans droit d'accès au jeu reçoit une **page inexistante** (`notFound()`) : l'API lui
 * répond déjà 404 sur toutes les routes du jeu (D11).
 *
 * L'écran ne décide rien : il règle. Le choix de l'image carte par carte est fait par le serveur,
 * et le veto « ne jamais montrer mes photos » y est appliqué — ici on ne fait que le poser et
 * **dire ce qu'il implique**, parce qu'un réglage de confidentialité qu'on ne comprend pas n'est
 * pas un réglage.
 */
export function RenduView() {
  const [refuse, setRefuse] = useState(false);
  const [reglages, setReglages] = useState<ReglagesRendu | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  // Autorité d'accès : `game_access` est lu côté serveur. Faux → page inexistante. Un échec de
  // lecture n'est PAS un refus : « je n'ai pas pu savoir » et « tu n'as pas le droit » diffèrent.
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

  useEffect(() => {
    if (refuse) return;
    let actif = true;
    getRenduSettings()
      .then((reg) => {
        if (actif) {
          setReglages(reg);
          setErreur(null);
        }
      })
      .catch((cause) => {
        // Jamais d'écran muet : on dit que le chargement a échoué plutôt que d'afficher des
        // réglages par défaut qui ne sont peut-être pas les siens.
        if (actif) setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
      });
    return () => {
      actif = false;
    };
  }, [refuse]);

  const regler = useCallback(
    async (patch: Parameters<typeof updateRenduSettings>[0]) => {
      setEnCours(true);
      try {
        setReglages(await updateRenduSettings(patch));
        setErreur(null);
      } catch (cause) {
        setErreur(cause instanceof ApiError ? cause.message : "Réglage impossible.");
      } finally {
        setEnCours(false);
      }
    },
    []
  );

  if (refuse) notFound();

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <h1 className="font-heading text-2xl font-extrabold">Mes cartes en jeu</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Tu peux jouer avec <strong>tes</strong> cartes — celles que tu as photographiées — ou avec
        les images officielles. Quand une photo manque ou qu&apos;elle est trop sombre, trop floue ou
        coupée, l&apos;image officielle prend le relais automatiquement : la partie ne s&apos;arrête
        jamais pour une photo.
      </p>

      {erreur && (
        <div className="mt-4">
          <FormNotice variant="error">{erreur}</FormNotice>
        </div>
      )}

      {reglages && (
        <>
          <section className="mt-8" aria-labelledby="titre-rendu-defaut">
            <h2 id="titre-rendu-defaut" className="font-heading text-lg font-bold">
              Par défaut, je joue avec
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Ce choix s&apos;applique à tous tes decks qui n&apos;ont pas le leur : chaque deck peut
              décider autrement.
            </p>
            <div className="mt-3 flex flex-col gap-2" role="radiogroup" aria-label="Rendu par défaut">
              {[RENDU_PHOTO, RENDU_OFFICIELLE].map((rendu) => (
                <label
                  key={rendu}
                  className="flex cursor-pointer items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm"
                >
                  <input
                    type="radio"
                    name="rendu_defaut"
                    value={rendu}
                    data-testid={`rendu-${rendu}`}
                    checked={reglages.rendu_defaut === rendu}
                    disabled={enCours}
                    onChange={() => void regler({ rendu_defaut: rendu })}
                  />
                  <span>{libelleRendu(rendu)}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="mt-8" aria-labelledby="titre-confidentialite">
            <h2 id="titre-confidentialite" className="font-heading text-lg font-bold">
              Ce que l&apos;adversaire voit
            </h2>
            <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                data-testid="jamais-montrer"
                checked={reglages.jamais_montrer_mes_photos}
                disabled={enCours}
                onChange={(e) =>
                  void regler({ jamais_montrer_mes_photos: e.currentTarget.checked })
                }
              />
              <span>
                <strong>Ne jamais montrer mes photos à l&apos;adversaire.</strong>
                <span className="mt-1 block text-xs text-muted-foreground">
                  Il verra les images officielles à la place. Toi, tu continues de voir tes propres
                  photos : ce réglage te protège, il ne te prive de rien.
                </span>
              </span>
            </label>
          </section>

          <p className="mt-8 text-xs text-muted-foreground">
            En partie, tes cartes sont envoyées en {reglages.largeur_jeu}×{reglages.hauteur_jeu}
            {" "}pixels — assez pour les lire en les agrandissant, assez léger pour que le plateau
            s&apos;affiche tout de suite.
          </p>
          <p className="mt-4">
            <Button type="button" variant="outline" asChild>
              <Link href="/jeu/decks">Voir mes decks</Link>
            </Button>
          </p>
        </>
      )}
    </main>
  );
}
