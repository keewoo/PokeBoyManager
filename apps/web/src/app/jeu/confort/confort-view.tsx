"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";
import { useConfort } from "@/lib/confort-provider";
import {
  ANIMATIONS,
  ANIMATIONS_REDUITES,
  TAILLES_TEXTE,
  libelleAnimations,
  libelleTailleTexte,
} from "@/lib/game/confort";
import { DECORS, DECORS_REGLABLES, momentPourHeure } from "@/lib/game/decors";

/**
 * Écran « Confort de jeu » (`/jeu/confort`, lot `j-accessibilite-jeu`) : quatre réglages, en
 * français d'enfant, et chacun dit ce qu'il change vraiment. Le quatrième, le **décor d'arène**
 * (lot `j-arene-decors`), est arrivé ici plutôt que sur un écran à lui : c'est la même sorte de
 * réglage que les trois autres — il ne change aucune règle, il suit le compte, et un enfant qui
 * cherche « comment c'est beau » et « comment ça bouge » les cherche au même endroit.
 *
 * Un compte sans droit d'accès au jeu reçoit une **page inexistante** (`notFound()`) : l'API lui
 * répond déjà 404 sur toutes les routes du jeu (D11).
 *
 * Les réglages vivent dans le fournisseur (`useConfort`), pas ici : ils s'appliquent à **tout** le
 * produit dès qu'on les touche, pas seulement à cet écran — on doit voir le texte grossir en
 * cliquant, sinon on ne sait pas ce qu'on a réglé. Le serveur les persiste (ils suivent le compte,
 * pas l'appareil) et c'est lui qui refuse une valeur inconnue.
 */
export function ConfortView() {
  const [refuse, setRefuse] = useState(false);
  const [erreurProfil, setErreurProfil] = useState<string | null>(null);
  const { confort, regler, erreur } = useConfort();

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
        if (actif) {
          setErreurProfil(cause instanceof ApiError ? cause.message : "Chargement impossible.");
        }
      });
    return () => {
      actif = false;
    };
  }, []);

  if (refuse) notFound();

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8">
      <h1 className="font-heading text-2xl font-extrabold">Confort de jeu</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Ces réglages suivent ton compte : tu les poses une fois, et ils te suivent sur tous tes
        écrans. Tu peux les changer quand tu veux, même entre deux parties.
      </p>

      {(erreurProfil || erreur) && (
        <div className="mt-4">
          <FormNotice variant="error">{erreurProfil ?? erreur}</FormNotice>
        </div>
      )}

      <section className="mt-8" aria-labelledby="titre-animations">
        <h2 id="titre-animations" className="font-heading text-lg font-bold">
          Les animations
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Si les mouvements te gênent ou te donnent mal à la tête, coupe-les : tu verras exactement
          la même partie, simplement sans rien qui bouge. Le journal continue de tout raconter.
        </p>
        <div
          className="mt-3 flex flex-col gap-2"
          role="radiogroup"
          aria-label="Réglage des animations"
        >
          {ANIMATIONS.map((valeur) => (
            <label
              key={valeur}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm"
            >
              <input
                type="radio"
                name="animations"
                value={valeur}
                data-testid={`confort-animations-${valeur}`}
                checked={confort.animations === valeur}
                onChange={() => void regler({ animations: valeur })}
              />
              <span>{libelleAnimations(valeur)}</span>
            </label>
          ))}
        </div>
        {confort.animations === ANIMATIONS_REDUITES && (
          <p className="mt-2 text-xs text-muted-foreground" data-testid="confort-anim-note">
            Pendant une partie, tu peux aussi sauter une animation à la fois, avec le bouton
            «&nbsp;Passer&nbsp;» en haut du plateau.
          </p>
        )}
      </section>

      <section className="mt-8" aria-labelledby="titre-texte">
        <h2 id="titre-texte" className="font-heading text-lg font-bold">
          La taille du texte
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Tout ce qui se lit grossit : les menus, le journal, l&apos;aide, tes decks. Les cartes du
          plateau, elles, gardent leur taille — le plateau doit tenir en entier sur l&apos;écran. Pour
          lire une carte en jeu, agrandis-la&nbsp;: elle s&apos;ouvre en grand.
        </p>
        <div
          className="mt-3 flex flex-col gap-2"
          role="radiogroup"
          aria-label="Taille du texte"
        >
          {TAILLES_TEXTE.map((valeur) => (
            <label
              key={valeur}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm"
            >
              <input
                type="radio"
                name="taille_texte"
                value={valeur}
                data-testid={`confort-texte-${valeur}`}
                checked={confort.taille_texte === valeur}
                onChange={() => void regler({ taille_texte: valeur })}
              />
              <span>{libelleTailleTexte(valeur)}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="mt-8" aria-labelledby="titre-decor">
        <h2 id="titre-decor" className="font-heading text-lg font-bold">
          Le décor de l&apos;arène
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          L&apos;endroit où tu joues. Tous les décors restent sombres exprès&nbsp;: ce qu&apos;on
          doit voir en premier, ce sont tes cartes. Le soir, le décor baisse sa lumière tout seul.
        </p>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3" role="radiogroup" aria-label="Décor de l'arène">
          {/* « Automatique » d'abord : c'est le défaut, et c'est le seul choix qui demande une
              explication — les cinq autres se montrent. */}
          <label
            className="flex cursor-pointer flex-col gap-2 rounded-2xl border border-[rgba(157,0,255,0.3)] p-2 text-xs"
            data-testid="confort-decor-option-auto"
          >
            <span className="pbm-decor-vignette flex items-center justify-center text-center text-[0.65rem] text-muted-foreground" data-decor="arene">
              selon mon deck
            </span>
            <span className="flex min-h-11 items-center gap-2">
              <input
                type="radio"
                name="decor"
                data-testid="confort-decor-auto"
                checked={confort.decor === null}
                // `null` explicite, et non l'absence du champ : c'est ce qui distingue « reviens
                // au thème automatique » de « ne touche pas à ce réglage ».
                onChange={() => void regler({ decor: null })}
              />
              <span>Automatique</span>
            </span>
          </label>
          {DECORS_REGLABLES.map((cle) => (
            <label
              key={cle}
              className="flex cursor-pointer flex-col gap-2 rounded-2xl border border-[rgba(157,0,255,0.3)] p-2 text-xs"
              data-testid={`confort-decor-option-${cle}`}
            >
              {/* La vignette porte `data-decor` : elle est peinte par le MÊME CSS que l'arène
                  (`globals.css`, bloc « Décors d'arène »), donc elle ne peut pas montrer autre
                  chose que ce qui sera joué. `data-decor-moment` suit l'heure, comme en partie. */}
              <span
                className="pbm-decor-vignette"
                data-decor={cle}
                data-decor-moment={momentPourHeure(new Date().getHours())}
                aria-hidden
              />
              <span className="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  name="decor"
                  value={cle}
                  data-testid={`confort-decor-${cle}`}
                  checked={confort.decor === cle}
                  onChange={() => void regler({ decor: cle })}
                />
                <span>{DECORS[cle]!.libelle}</span>
              </span>
              <span className="text-[0.7rem] text-muted-foreground">{DECORS[cle]!.phrase}</span>
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground" data-testid="confort-decor-note">
          En <strong>automatique</strong>, le jeu regarde les cartes de ton deck et choisit
          l&apos;endroit qui leur va&nbsp;: un volcan pour le Feu, un lagon pour l&apos;Eau. Si tu
          choisis un décor toi-même, c&apos;est le tien qui gagne, toujours.
        </p>
      </section>

      <section className="mt-8" aria-labelledby="titre-temps">
        <h2 id="titre-temps" className="font-heading text-lg font-bold">
          Le temps pour réfléchir
        </h2>
        <label className="mt-3 flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            data-testid="confort-temps-rallonge"
            checked={confort.temps_rallonge}
            onChange={(e) => void regler({ temps_rallonge: e.currentTarget.checked })}
          />
          <span>
            <strong>J&apos;ai besoin de plus de temps.</strong>
            <span className="mt-1 block text-xs text-muted-foreground">
              Les horloges de tes parties sont <strong>doublées</strong> : deux fois plus de temps
              pour jouer ton tour, et pour répondre quand le jeu te pose une question. Ça vaut pour
              tes <strong>prochaines</strong> parties — une partie déjà commencée garde ses horloges.
              Et si ton adversaire l&apos;a demandé, vous l&apos;avez tous les deux : le jeu suit
              toujours celui qui a besoin de plus de temps.
            </span>
          </span>
        </label>
      </section>

      <p className="mt-8 text-xs text-muted-foreground">
        Si ton téléphone ou ton ordinateur demande déjà «&nbsp;moins d&apos;animations&nbsp;» dans
        ses propres réglages, le jeu le respecte, même si tu as choisi de les montrer ici.
      </p>
      {/* Le son n'est PAS ici, et le dire est le seul moyen d'éviter qu'on le cherche : il se règle
          par appareil (DJ9), pas par compte, contrairement aux quatre réglages de cette page. */}
      <p className="mt-2 text-xs text-muted-foreground" data-testid="confort-vers-sons">
        Le <strong>son</strong> se règle ailleurs&nbsp;:{" "}
        <Link href="/jeu/sons" className="underline">
          Les sons du jeu
        </Link>
        . Il reste sur l&apos;appareil que tu utilises, alors que les réglages de cette page te
        suivent partout.
      </p>
      <p className="mt-4 flex flex-wrap gap-2">
        <Button type="button" variant="outline" asChild>
          <Link href="/jeu/salon">Retour au salon</Link>
        </Button>
        <Button type="button" variant="outline" asChild>
          <Link href="/jeu/sons">Les sons du jeu</Link>
        </Button>
        <Button type="button" variant="outline" asChild>
          <Link href="/jeu/rendu">Mes cartes en jeu</Link>
        </Button>
      </p>
    </main>
  );
}
