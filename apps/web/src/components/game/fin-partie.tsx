"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import { useModale } from "@/lib/game/use-modale";
import {
  getRecapitulatif,
  listGames,
  revancheGame,
  type Recapitulatif,
  type StatsJoueur,
} from "@/lib/api/games";
import {
  bilanCompte,
  dureeEnFrancais,
  issueDeFin,
  phraseDeFin,
  raisonCourte,
  titreDeFin,
  type BilanCompte,
} from "@/lib/game/fin";

/**
 * L'écran de fin de partie (lot `j-partie-fin-ui`, jalon J4) : qui a gagné, pourquoi, et ce qu'on
 * en retient.
 *
 * **Il est posé hors du flux** (`fixed inset-0`), et c'est une contrainte, pas une préférence : la
 * page du plateau ne tolère **aucun** défilement (e2e `plateau-responsive.spec.ts` — un
 * `documentElement` plus haut que la fenêtre fait échouer le job). Un panneau en flux normal
 * allongerait la page sans qu'aucun test unitaire ne s'en aperçoive. Le panneau a donc son propre
 * défilement interne (`overflow-y-auto`), qui ne touche pas celui du document — même motif que le
 * tiroir du journal et la barre du replay.
 *
 * **Tous les chiffres viennent du serveur**, qui les recalcule depuis le journal
 * (`GET /games/{id}/recapitulatif`). L'écran n'en compte aucun : c'est le risque nommé du lot —
 * le canal temps réel rejoue la partie entière à chaque reconnexion, donc un compteur tenu ici
 * doublerait après un F5.
 *
 * **Le vainqueur aussi vient de là.** La vue du plateau porte bien `vainqueur`, mais c'est un
 * identifiant **moteur** ; le récapitulatif donne le `vainqueur_user_id`, du même espace de noms
 * que le compte connecté. Comparer les deux espaces donnerait, un jour, la victoire au mauvais
 * joueur — on ne les mélange pas.
 *
 * **Le perdant n'est pas humilié** : chaque raison de fin a trois phrases, une par issue
 * (`pbm/lib/game/fin.ts`), et celle de la défaite énonce un fait, jamais un jugement.
 *
 * Si le récapitulatif ne se charge pas, on l'écrit (`FormNotice`) et on annonce quand même la fin
 * avec la raison que le plateau connaît : une fin sans annonce serait une panne muette. En
 * revanche on n'invente **ni chiffre ni résultat** — sans le récapitulatif, le vainqueur est
 * inconnu, et un « inconnu » replié sur « match nul » serait un faux résultat affiché avec
 * aplomb. On dit « Partie terminée », et on nomme la raison.
 */
export function FinPartie({
  gameId,
  moiUserId,
  raisonFinVue,
}: {
  gameId: string;
  /** L'identifiant du **compte** connecté (`profile.id`), pas l'identifiant moteur du joueur. */
  moiUserId: string;
  /** La raison de fin telle que le plateau la connaît : le repli d'annonce si le récap échoue. */
  raisonFinVue: string | null;
}) {
  const router = useRouter();
  const [recap, setRecap] = useState<Recapitulatif | null>(null);
  const [bilan, setBilan] = useState<BilanCompte | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [replie, setReplie] = useState(false);
  const [revancheEnCours, setRevancheEnCours] = useState(false);
  const [erreurRevanche, setErreurRevanche] = useState<string | null>(null);

  // Le récapitulatif, et ce que la partie laisse sur le compte. Deux lectures indépendantes : un
  // historique indisponible ne doit pas empêcher d'annoncer le résultat.
  useEffect(() => {
    let actif = true;
    getRecapitulatif(gameId)
      .then((r) => {
        if (actif) setRecap(r);
      })
      .catch(() => {
        if (actif) setErreur("Le résumé de la partie n'a pas pu être chargé.");
      });
    listGames()
      .then((parties) => {
        if (actif) setBilan(bilanCompte(parties, moiUserId));
      })
      .catch(() => {
        // L'historique est un bonus : son absence se voit (la section ne s'affiche pas), elle ne
        // masque rien du résultat. On ne double pas le message d'erreur pour autant.
      });
    return () => {
      actif = false;
    };
  }, [gameId, moiUserId]);

  const onRevanche = useCallback(async () => {
    setErreurRevanche(null);
    setRevancheEnCours(true);
    try {
      const { game_id } = await revancheGame(gameId);
      router.push(`/jeu/parties/${game_id}`);
    } catch (err) {
      // Le serveur dit pourquoi (deck vendu, adversaire déjà en partie) : on le répète tel quel
      // plutôt qu'un « réessaie » qui n'apprendrait rien.
      setErreurRevanche(
        err instanceof ApiError
          ? err.message
          : "La revanche n'a pas pu être lancée. Réessaie dans un instant.",
      );
      setRevancheEnCours(false);
    }
  }, [gameId, router]);

  const raison = recap?.raison_fin ?? raisonFinVue;
  // L'issue vient du récapitulatif, et de lui seul. Tant qu'il n'est pas arrivé, on ne la connaît
  // **pas** — et « inconnue » ne se replie pas sur « match nul » : annoncer une partie nulle
  // alors qu'on ignore le vainqueur serait un faux résultat, affiché avec aplomb. On dit donc
  // « Partie terminée », et on nomme la raison, qui elle est connue du plateau.
  const issue = recap ? issueDeFin(recap.vainqueur_user_id, moiUserId) : null;

  // Clavier de la surcouche (lot `j-accessibilite-jeu`) : **Échap** replie le résumé, le **Tab** y
  // reste tant qu'il est ouvert. `actif: !replie` — replié, ce n'est plus qu'un bouton dans un
  // coin, il n'y a rien à piéger ni à fermer ; et le focus est repris quand on le redéploie, sinon
  // au clavier il tombait sur le `<body>` au moment où le bouton disparaissait.
  const refModale = useModale({ onFermer: () => setReplie(true), actif: !replie });

  if (replie) {
    return (
      <button
        type="button"
        onClick={() => setReplie(false)}
        data-testid="fin-partie-rouvrir"
        className="pbm-surface-or fixed bottom-3 left-3 z-40 rounded-md px-3 py-2 text-xs text-gold"
      >
        Partie terminée — revoir le résumé
      </button>
    );
  }

  return (
    <div
      ref={refModale}
      role="dialog"
      aria-modal="true"
      aria-labelledby="fin-partie-titre"
      data-testid="fin-partie"
      className="fixed inset-0 z-40 flex items-center justify-center overflow-y-auto bg-[rgba(3,6,28,0.82)] p-3"
    >
      <div className="pbm-surface pbm-halo-or w-full max-w-md space-y-3 rounded-lg p-4">
        <h2 id="fin-partie-titre" data-testid="fin-partie-titre" className="pbm-titre text-sm">
          {issue ? titreDeFin(issue) : "Partie terminée"}
        </h2>

        <p data-testid="fin-partie-raison" className="text-sm">
          {issue
            ? phraseDeFin(raison, issue)
            : erreur
              ? `Fin de partie : ${raisonCourte(raison)}. Le résultat détaillé n'a pas pu être chargé.`
              : "Résumé de la partie en cours de chargement…"}
        </p>
        <p className="text-xs text-muted-foreground" data-testid="fin-partie-raison-courte">
          Fin de partie : {raisonCourte(raison)}
        </p>

        {erreur && <FormNotice variant="error">{erreur}</FormNotice>}

        {recap && <Recap recap={recap} moiUserId={moiUserId} />}
        {recap?.entrainement && (
          <p className="text-xs text-muted-foreground" data-testid="fin-partie-entrainement">
            Partie d&apos;entraînement : elle reste dans ton historique, mais elle ne compte pas
            dans tes statistiques.
          </p>
        )}

        {bilan && !recap?.entrainement && (
          <section
            className="pbm-surface-or space-y-1 rounded-md p-3 text-xs"
            data-testid="fin-partie-compte"
          >
            <h3 className="pbm-section text-xs">Sur ton compte</h3>
            <p>
              {bilan.parties} partie{bilan.parties > 1 ? "s" : ""} jouée
              {bilan.parties > 1 ? "s" : ""}, {bilan.victoires} gagnée
              {bilan.victoires > 1 ? "s" : ""}.
            </p>
            <p data-testid="fin-partie-serie">
              {bilan.serie > 0
                ? `Série en cours : ${bilan.serie} victoire${bilan.serie > 1 ? "s" : ""} d'affilée.`
                : "Aucune série en cours."}
            </p>
            <Link href="/jeu/salon" className="underline">
              Voir mes parties
            </Link>
          </section>
        )}

        {erreurRevanche && <FormNotice variant="error">{erreurRevanche}</FormNotice>}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onRevanche}
            disabled={revancheEnCours}
            data-testid="fin-partie-revanche"
            className="pbm-surface-or rounded-md px-3 py-2 text-sm text-gold disabled:opacity-60"
          >
            {revancheEnCours ? "On relance…" : "Revanche"}
          </button>
          <Link
            href={`/jeu/parties/${gameId}/replay`}
            data-testid="fin-partie-replay"
            className="pbm-surface rounded-md px-3 py-2 text-sm"
          >
            Revoir la partie
          </Link>
          <Link
            href="/jeu/salon"
            data-testid="fin-partie-salon"
            className="pbm-surface rounded-md px-3 py-2 text-sm"
          >
            Retour au salon
          </Link>
          <button
            type="button"
            onClick={() => setReplie(true)}
            data-testid="fin-partie-replier"
            className="rounded-md px-3 py-2 text-sm underline"
          >
            Voir le plateau
          </button>
        </div>
      </div>
    </div>
  );
}

/** Le nom à afficher pour un siège : son pseudo, « Toi » pour le joueur connecté, sinon un repli. */
function nomDu(siege: StatsJoueur, moiUserId: string): string {
  if (siege.user_id === moiUserId) return "Toi";
  return siege.pseudo ?? "Adversaire";
}

/**
 * Le tableau du récapitulatif : les chiffres globaux, puis une colonne par joueur.
 *
 * Un vrai `<table>` : ce sont des données tabulaires, et un lecteur d'écran a besoin des en-têtes
 * de colonne pour dire « Toi, dégâts infligés, 180 ». Les chiffres ne sont jamais recalculés ici —
 * ils sont affichés tels que le serveur les a comptés depuis le journal.
 */
function Recap({ recap, moiUserId }: { recap: Recapitulatif; moiUserId: string }) {
  const lignes: Array<[string, (s: StatsJoueur) => number]> = [
    ["Dégâts infligés", (s) => s.degats_infliges],
    ["Pokémon mis K.O.", (s) => s.kos_infliges],
    ["Récompenses prises", (s) => s.recompenses_prises],
    ["Cartes jouées", (s) => s.cartes_jouees],
    ["Énergies attachées", (s) => s.energies_attachees],
    ["Coups joués", (s) => s.coups_joues],
  ];
  const meilleur = recap.meilleur_coup;
  const auteurMeilleur =
    meilleur === null
      ? null
      : (recap.joueurs.find((j) => j.user_id === meilleur.user_id) ?? null);

  return (
    <section className="space-y-2" data-testid="fin-partie-recap">
      <h3 className="pbm-section text-xs">Ce qui s&apos;est passé</h3>
      <p className="text-xs" data-testid="fin-partie-global">
        Durée : {dureeEnFrancais(recap.duree_s)} · {recap.tours} tour
        {recap.tours > 1 ? "s" : ""} · {recap.coups} coup{recap.coups > 1 ? "s" : ""}
      </p>
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th scope="col" className="text-left font-normal text-muted-foreground">
              &nbsp;
            </th>
            {recap.joueurs.map((siege) => (
              <th key={siege.user_id} scope="col" className="text-right font-normal">
                {nomDu(siege, moiUserId)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map(([libelle, valeur]) => (
            <tr key={libelle}>
              <th scope="row" className="text-left font-normal text-muted-foreground">
                {libelle}
              </th>
              {recap.joueurs.map((siege) => (
                <td key={siege.user_id} className="text-right">
                  {valeur(siege)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {meilleur !== null && (
        <p className="text-xs" data-testid="fin-partie-meilleur-coup">
          Meilleur coup : {auteurMeilleur ? nomDu(auteurMeilleur, moiUserId) : "un joueur"} au coup
          n° {meilleur.numero}, {meilleur.degats} dégâts
          {meilleur.ko ? " — et c'était un K.O." : ""}.
        </p>
      )}
    </section>
  );
}
