"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import { getProfile } from "@/lib/api/profile";
import { SONS, type CleSon } from "@/lib/game/sons";
import { useSons } from "@/lib/sons-provider";

/**
 * Écran « Les sons du jeu » (`/jeu/sons`, lot `j-son`) : deux interrupteurs, un volume, et la
 * **banque entière, écoutable**.
 *
 * ## Pourquoi un écran à part, et pas une section de `/jeu/confort`
 *
 * Parce que ce réglage n'est pas de la même nature. Le confort (animations, taille du texte, décor)
 * suit le **compte** : on le pose une fois et il voyage. Le son suit l'**appareil** (DJ9), et il n'y
 * a pas d'autre choix raisonnable — le volume supportable dépend de l'endroit, pas de la personne.
 * Les mettre côte à côte aurait laissé croire qu'ils se comportent pareil, et quelqu'un aurait
 * cherché pendant dix minutes pourquoi « son coupé » ne l'a pas suivi sur la tablette.
 *
 * ## Pourquoi on peut écouter chaque son
 *
 * Deux raisons, et aucune n'est cosmétique. D'abord pour **régler** : on ne choisit pas un volume
 * dans l'abstrait, on l'essaie — et le son qu'il faut essayer est le plus fort (le K.O.), pas le
 * plus discret. Ensuite pour **vérifier** : c'est ici qu'on entend qu'un son est devenu agressif
 * après une retouche, ce qu'aucun test ne saura jamais dire. C'est le pendant sonore de la galerie
 * d'effets (`/jeu/effets`).
 *
 * Et le premier clic sur n'importe quel bouton de cette page est **le geste** qui ouvre le son : la
 * page est donc aussi l'endroit le plus naturel pour que le son commence à exister.
 */

/** Les sons regroupés par moment de jeu, pour qu'on les retrouve comme on les entend. */
const GROUPES: { titre: string; aide: string; sons: CleSon[] }[] = [
  {
    titre: "Ce que tu fais de tes mains",
    aide: "Poser, piocher, attacher une Énergie, jouer une carte Dresseur. Ce sont les plus discrets : ce sont eux qu'on entend le plus souvent.",
    sons: ["pose", "pioche", "energie", "objet", "talent", "evolution"],
  },
  {
    titre: "Les échanges de coups",
    aide: "L'attaque part, le coup porte — ou rate. Le son du coup change avec le type d'Énergie et avec les dégâts réellement infligés, comme l'effet à l'écran.",
    sons: ["attaque", "impact", "echec", "ko", "recompense"],
  },
  {
    titre: "Le rythme de la partie",
    aide: "Le hasard, ton tour, et le temps qui presse. La minuterie est volontairement le son le plus discret de tout le jeu, et elle ne sonne qu'une fois.",
    sons: ["piece", "tour", "minuterie"],
  },
  {
    titre: "La fin",
    aide: "Les seuls sons qui ont le droit de durer une seconde : la partie est finie, ils ne couvrent plus rien.",
    sons: ["victoire", "defaite", "egalite"],
  },
];

export function SonsView() {
  const [refuse, setRefuse] = useState(false);
  const [erreurProfil, setErreurProfil] = useState<string | null>(null);
  const { reglages, regler, jouer, pret } = useSons();

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
      <h1 className="font-heading text-2xl font-extrabold">Les sons du jeu</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Ces réglages restent <strong>sur cet appareil</strong>&nbsp;: ils ne suivent pas ton compte.
        C&apos;est voulu — le volume qui va bien dans ta chambre n&apos;est pas celui qui va bien
        dans le train. Pour les réglages qui te suivent partout (animations, taille du texte,
        décor), c&apos;est{" "}
        <Link href="/jeu/confort" className="underline">
          Confort de jeu
        </Link>
        .
      </p>

      {erreurProfil && (
        <div className="mt-4">
          <FormNotice variant="error">{erreurProfil}</FormNotice>
        </div>
      )}

      <section className="mt-8" aria-labelledby="titre-reglages">
        <h2 id="titre-reglages" className="font-heading text-lg font-bold">
          Ce que tu entends
        </h2>

        <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm">
          <input
            type="checkbox"
            data-testid="sons-bruitages"
            checked={reglages.bruitages}
            onChange={(e) => regler({ bruitages: e.target.checked })}
          />
          <span>
            <strong>Les bruitages</strong> — les cartes, les attaques, les K.O. Pendant une partie,
            tu peux aussi les couper d&apos;un clic, en haut à gauche du plateau.
          </span>
        </label>

        <label className="mt-2 flex min-h-11 cursor-pointer items-center gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3 text-sm">
          <input
            type="checkbox"
            data-testid="sons-musique"
            checked={reglages.musique}
            onChange={(e) => regler({ musique: e.target.checked })}
          />
          <span>
            <strong>La musique de fond</strong> — une phrase très douce, qui tourne lentement. Elle
            est coupée au départ&nbsp;: on ne met pas de musique à quelqu&apos;un qui n&apos;en a
            pas demandé.
          </span>
        </label>

        <div className="mt-4">
          <label htmlFor="sons-volume" className="text-sm font-semibold">
            Le volume général
          </label>
          <input
            id="sons-volume"
            type="range"
            min={0}
            max={100}
            step={5}
            data-testid="sons-volume"
            value={Math.round(reglages.volume * 100)}
            onChange={(e) => regler({ volume: Number(e.target.value) / 100 })}
            className="mt-2 w-full"
            aria-valuetext={`${Math.round(reglages.volume * 100)} %`}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Le volume de ton appareil s&apos;applique par-dessus&nbsp;: si ton téléphone est en
            silencieux, le jeu reste muet, et c&apos;est normal — on ne passe pas outre.
          </p>
        </div>
      </section>

      <section className="mt-10" aria-labelledby="titre-banque">
        <h2 id="titre-banque" className="font-heading text-lg font-bold">
          Écouter tous les sons
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Appuie pour entendre. {pret ? "Le son est prêt." : "Le premier appui allume le son."}
        </p>

        {GROUPES.map((groupe) => (
          <div key={groupe.titre} className="mt-6">
            <h3 className="font-heading text-sm font-bold">{groupe.titre}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{groupe.aide}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {groupe.sons.map((cle) => (
                <button
                  key={cle}
                  type="button"
                  data-testid={`sons-essai-${cle}`}
                  onClick={() => jouer(SONS[cle])}
                  className="min-h-11 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-2 text-left text-xs hover:border-[rgba(157,0,255,0.6)]"
                >
                  <span className="block font-semibold">{SONS[cle].libelle}</span>
                  <span className="block text-muted-foreground">{SONS[cle].duree} ms</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="mt-10" aria-labelledby="titre-origine">
        <h2 id="titre-origine" className="font-heading text-lg font-bold">
          D&apos;où viennent ces sons
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          D&apos;ici. Aucun n&apos;a été téléchargé&nbsp;: il n&apos;y a pas un seul fichier audio
          dans ce jeu. Chaque son est une <strong>recette</strong> écrite dans le code — des formes
          d&apos;onde, des fréquences, une montée et une descente — et c&apos;est ton navigateur qui
          le fabrique au moment où tu l&apos;entends.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          C&apos;était le choix le plus simple à tenir&nbsp;: un bruitage pris sur un site
          d&apos;échantillons, même gratuit, demande qu&apos;on garde la trace de sa licence pour
          toujours. Là, il n&apos;y a rien à créditer, et rien à re-sourcer le jour où un site
          disparaît. La recette de chaque son est dans{" "}
          <code className="rounded bg-black/20 px-1">apps/web/src/lib/game/sons.ts</code>.
        </p>
      </section>
    </main>
  );
}
