"use client";

import { notFound } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { CardImage } from "@/components/card-image";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { listCollection, type CollectionListItem } from "@/lib/api/collection";
import { avatarUrl, getProfile } from "@/lib/api/profile";
import {
  getProfilJeu,
  libelleMesure,
  poserCarteFetiche,
  type BadgeJoueur,
  type ProfilJeu,
} from "@/lib/api/profil-jeu";
import { libelleDecor } from "@/lib/game/decors";

/** Combien de cartes de la collection la recherche de carte fétiche propose à la fois. */
const CARTES_PROPOSEES = 12;

/**
 * Une ligne de badge : son nom, ce qu'il récompense, et s'il est obtenu.
 *
 * Les badges **non obtenus** sont montrés aussi, avec leur description : c'est ce qui donne un
 * objectif lisible (« gagne sans céder une récompense ») au lieu d'une collection mystérieuse. Rien
 * n'est caché, rien n'est aléatoire — il n'y a aucune surprise à acheter.
 */
function LigneBadge({ badge }: { badge: BadgeJoueur }) {
  return (
    <li
      data-testid="badge"
      data-code={badge.code}
      data-obtenu={badge.obtenu ? "oui" : "non"}
      className={
        badge.obtenu
          ? "rounded-2xl border border-[rgba(255,196,0,0.55)] bg-[rgba(255,196,0,0.07)] px-4 py-3"
          : "rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 opacity-70"
      }
    >
      <p className="flex items-center gap-2 text-sm font-semibold">
        <span aria-hidden="true">{badge.obtenu ? "★" : "☆"}</span>
        <span>{badge.nom}</span>
        <span className="text-xs font-normal text-[#C77DFF]">{libelleMesure(badge.mesure)}</span>
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{badge.description}</p>
      {badge.obtenu && badge.obtenu_a && (
        <p className="mt-1 text-xs text-muted-foreground">
          Obtenu le{" "}
          {new Date(badge.obtenu_a).toLocaleDateString("fr-FR", {
            day: "numeric",
            month: "long",
            year: "numeric",
          })}
        </p>
      )}
      {!badge.obtenu && (
        // Lu par les lecteurs d'écran : l'étoile creuse ne dit rien à qui ne la voit pas.
        <span className="sr-only">Pas encore obtenu.</span>
      )}
    </li>
  );
}

/**
 * Vitrine du profil de joueur (`/jeu/profil`, lot `j-profil-jeu`, décision DJ6).
 *
 * Trois choses, et aucune n'est une récompense monnayable : l'**identité** reprise du compte
 * (pseudo, avatar — il n'existe pas de pseudo de jeu distinct), la **carte fétiche** qu'on montre à
 * son adversaire au lancement, et les **badges** quand JF les a allumés.
 *
 * ⚠️ L'écran ne décide d'**aucun** rendu d'image : l'URL de la carte fétiche vient du serveur, qui
 * a déjà arbitré photo/officielle pour le regard de l'adversaire (DJ5). Si l'écran choisissait, le
 * veto « ne jamais montrer mes photos » serait contournable depuis le navigateur. La vitrine montre
 * donc **ce que l'adversaire verra**, ce qui est l'information utile.
 *
 * Un compte sans droit d'accès au jeu reçoit une **page inexistante** (`notFound()`) : l'API lui
 * répond déjà 404 sur toutes les routes du jeu (D11).
 */
export function ProfilJeuView() {
  const [refuse, setRefuse] = useState(false);
  const [profil, setProfil] = useState<ProfilJeu | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [recherche, setRecherche] = useState("");
  const [cartes, setCartes] = useState<CollectionListItem[] | null>(null);
  const [enCours, setEnCours] = useState(false);

  // Autorité d'accès : `game_access` est lu côté serveur. Faux → page inexistante. Un échec de
  // lecture n'est PAS un refus : « je n'ai pas pu savoir » et « tu n'as pas le droit » diffèrent.
  useEffect(() => {
    let actif = true;
    getProfile()
      .then((compte) => {
        if (!actif) return;
        if (!compte.game_access) setRefuse(true);
      })
      .catch((cause) => {
        if (actif) setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
      });
    return () => {
      actif = false;
    };
  }, []);

  useEffect(() => {
    let actif = true;
    getProfilJeu()
      .then((vitrine) => {
        if (actif) setProfil(vitrine);
      })
      .catch((cause) => {
        if (actif) setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
      });
    return () => {
      actif = false;
    };
  }, []);

  const chercher = useCallback(async () => {
    setErreur(null);
    try {
      const page = await listCollection({ q: recherche, limit: CARTES_PROPOSEES });
      setCartes(page.items);
    } catch (cause) {
      setErreur(cause instanceof ApiError ? cause.message : "Recherche impossible.");
    }
  }, [recherche]);

  const choisir = useCallback(async (cardId: string | null) => {
    setErreur(null);
    setEnCours(true);
    try {
      // Le serveur rend la vitrine complète : on la remplace plutôt que de la rapiécer, pour que
      // l'écran ne puisse pas afficher un état que le serveur n'a pas validé.
      setProfil(await poserCarteFetiche(cardId));
      setCartes(null);
    } catch (cause) {
      // Le message du 422 est écrit pour le joueur (« cette carte n'est pas dans ta collection ») :
      // on l'affiche tel quel plutôt que de le traduire une seconde fois.
      setErreur(cause instanceof ApiError ? cause.message : "Choix impossible.");
    } finally {
      setEnCours(false);
    }
  }, []);

  if (refuse) notFound();

  return (
    <main data-testid="profil-jeu" className="mx-auto w-full max-w-3xl px-4 py-8">
      <h1 className="font-heading text-2xl font-extrabold uppercase tracking-[0.08em] text-gold">
        Mon profil de joueur
      </h1>

      {erreur && (
        <div className="mt-4">
          <FormNotice variant="error">{erreur}</FormNotice>
        </div>
      )}

      <section className="mt-6 flex items-center gap-4" aria-labelledby="titre-identite">
        <h2 id="titre-identite" className="sr-only">
          Mon identité
        </h2>
        {profil?.a_un_avatar ? (
          // eslint-disable-next-line @next/next/no-img-element -- avatar servi par l'API avec le
          // cookie de session (`crossOrigin`), hors du domaine d'optimisation de next/image.
          <img
            src={avatarUrl()}
            alt="Ma photo de profil"
            crossOrigin="use-credentials"
            className="h-16 w-16 rounded-full border border-[rgba(157,0,255,0.5)] object-cover"
          />
        ) : (
          <div
            aria-hidden="true"
            className="flex h-16 w-16 items-center justify-center rounded-full border border-dashed border-[rgba(157,0,255,0.5)] text-xl"
          >
            ?
          </div>
        )}
        <div>
          <p data-testid="pseudo" className="text-lg font-semibold">
            {profil?.pseudo ?? "Sans pseudo"}
          </p>
          <p className="text-xs text-muted-foreground">
            Ton pseudo et ta photo viennent de ton compte : tu les changes dans ton profil.
          </p>
        </div>
      </section>

      <section className="mt-8" aria-labelledby="titre-fetiche">
        <h2
          id="titre-fetiche"
          className="font-heading text-sm font-semibold uppercase tracking-[0.08em]"
        >
          Ma carte fétiche
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          C'est la carte que ton adversaire verra au moment de lancer la partie. Choisis-la parmi
          les cartes de ta collection.
        </p>

        {profil?.carte_fetiche ? (
          <div
            data-testid="carte-fetiche"
            data-card-id={profil.carte_fetiche.card_id}
            className="mt-3 flex items-center gap-4 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3"
          >
            <CardImage
              src={profil.carte_fetiche.rendu.url}
              alt={profil.carte_fetiche.nom}
              label="Pas d'image"
              className="h-24 w-[68px] shrink-0 rounded-sm object-cover"
            />
            <div className="min-w-0">
              <p className="text-sm font-semibold">{profil.carte_fetiche.nom}</p>
              {profil.carte_fetiche.rendu.raison && (
                <p data-testid="raison-rendu" className="mt-1 text-xs text-muted-foreground">
                  Ton adversaire verra l'image officielle : {profil.carte_fetiche.rendu.raison}.
                </p>
              )}
              <Button
                type="button"
                variant="outline"
                className="mt-2"
                disabled={enCours}
                onClick={() => choisir(null)}
                data-testid="retirer-fetiche"
              >
                Retirer ma carte fétiche
              </Button>
            </div>
          </div>
        ) : (
          <p data-testid="sans-fetiche" className="mt-3 text-sm text-muted-foreground">
            Tu n'as pas encore choisi de carte fétiche.
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="flex min-h-11 flex-col gap-1 text-xs" htmlFor="recherche-fetiche">
            Chercher dans ma collection
            <input
              id="recherche-fetiche"
              data-testid="recherche-fetiche"
              value={recherche}
              onChange={(evenement) => setRecherche(evenement.target.value)}
              className="min-h-11 rounded-full border border-[rgba(157,0,255,0.65)] bg-transparent px-4 py-2 text-sm"
              placeholder="Pikachu…"
            />
          </label>
          <Button type="button" variant="outline" onClick={chercher} data-testid="chercher-fetiche">
            Chercher
          </Button>
        </div>

        {cartes !== null && (
          <ul className="mt-3 space-y-2" data-testid="cartes-proposees">
            {cartes.length === 0 && (
              <li className="text-sm text-muted-foreground">
                Aucune carte de ta collection ne correspond.
              </li>
            )}
            {cartes.map((carte) => (
              <li
                key={carte.id}
                data-testid="carte-proposee"
                className="flex items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-2"
              >
                <span className="min-w-0 flex-1 truncate text-sm">
                  {carte.card_name}{" "}
                  <span className="text-xs text-muted-foreground">
                    {carte.set_name} · {carte.card_number}
                  </span>
                </span>
                <Button
                  type="button"
                  variant="outline"
                  disabled={enCours}
                  onClick={() => choisir(carte.card_id)}
                  aria-label={`Choisir ${carte.card_name} comme carte fétiche`}
                >
                  Choisir
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-8" aria-labelledby="titre-badges">
        <h2
          id="titre-badges"
          className="font-heading text-sm font-semibold uppercase tracking-[0.08em]"
        >
          Mes badges
        </h2>
        {profil && !profil.badges_actifs ? (
          <p data-testid="badges-eteints" className="mt-2 text-sm text-muted-foreground">
            Les badges ne sont pas activés pour l'instant. Rien n'est perdu : ce que tu gagnes est
            enregistré, et ils apparaîtront ici le jour où ils seront allumés.
          </p>
        ) : (
          <>
            <p className="mt-1 text-xs text-muted-foreground">
              Des badges gratuits, qui récompensent ce que tu fais en jeu — jamais le temps que tu y
              passes. Aucun ne s'achète, aucun ne se tire au sort.
            </p>
            <ul className="mt-3 space-y-2">
              {(profil?.badges ?? []).map((badge) => (
                <LigneBadge key={badge.code} badge={badge} />
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="mt-8" aria-labelledby="titre-decors">
        <h2
          id="titre-decors"
          className="font-heading text-sm font-semibold uppercase tracking-[0.08em]"
        >
          Mes décors
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Les six décors sont à toi dès maintenant : il n'y en a aucun à débloquer. Tu choisis celui
          de ton arène dans « Confort de jeu ».
        </p>
        <ul className="mt-3 flex flex-wrap gap-2" data-testid="decors">
          {(profil?.decors ?? []).map((decor) => (
            <li
              key={decor}
              data-decor={decor}
              data-choisi={profil?.decor_choisi === decor ? "oui" : "non"}
              className={
                profil?.decor_choisi === decor
                  ? "rounded-full border border-[rgba(255,196,0,0.55)] px-4 py-2 text-xs"
                  : "rounded-full border border-[rgba(157,0,255,0.45)] px-4 py-2 text-xs"
              }
            >
              {libelleDecor(decor)}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
