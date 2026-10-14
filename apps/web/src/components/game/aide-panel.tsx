"use client";

import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import {
  EXPLICATIONS,
  GLOSSAIRE,
  OBJECTIF,
  expliquerRefus,
  suggestions,
} from "@/lib/game/aide";
import { ETAPES_GUIDE, avancerGuide } from "@/lib/game/guide";
import { estMonTour, type VuePartie } from "@/lib/game/plateau";

/**
 * L'**aide en jeu** (lot `j-plateau-aide`) : pourquoi je ne peux pas faire ça, et que puis-je faire.
 *
 * Elle répond aux trois critères d'acceptation du lot, et chacun se lit dans le code :
 *
 * - **Tout refus est expliqué.** Le moteur refuse en citant une règle (`R-x.y`) ; l'aide traduit
 *   cette règle en une phrase d'enfant et nomme ce qu'on peut faire à la place. Un refus ouvre le
 *   tiroir **de lui-même** : un enfant ne va pas chercher l'aide, c'est l'aide qui vient à lui.
 * - **La première partie se guide pas à pas** : poser, attacher, attaquer, prendre une récompense.
 * - **L'aide ne joue jamais à la place du joueur.** Ce composant ne reçoit **aucune** fonction de
 *   jeu : regarde ses props, il n'y a rien qui puisse soumettre un coup. Il affiche, il n'agit pas.
 *
 * **Tiroir hors du flux**, comme le journal de partie : le plateau remplit l'écran d'un téléphone et
 * ne tolère aucun défilement (e2e `plateau-responsive`). Le tiroir est donc `fixed` — il n'allonge
 * jamais la page, quoi qu'il contienne.
 *
 * **En haut à GAUCHE, et borné à 15rem : c'est une contrainte, pas un goût.** Les quatre coins du
 * plateau sont déjà pris, et deux d'entre eux portent des boutons que l'e2e clique vraiment :
 *
 * | Coin | Qui l'occupe |
 * |---|---|
 * | haut gauche | **libre** (le statut de connexion est centré, `game-board.tsx`) |
 * | haut droite | `anim-accelere` / `anim-sauter` (`animation-layer.tsx`, `absolute right-2 top-2`) |
 * | bas, pleine largeur | le journal de partie (`journal-panel.tsx`) |
 * | bas gauche | l'écran de fin replié (`fin-partie.tsx`) |
 *
 * Posé en haut à droite, ce tiroir **recouvrait `anim-sauter`** sur l'écran de référence du jeu
 * (844 × 390, téléphone en paysage) : `anim-fluidite.spec.ts` le clique, et Playwright aurait
 * échoué sur une interception de clic — un défaut invisible en vitest comme en `tsc`, exactement le
 * mode de panne que ce dépôt connaît déjà. La largeur est bornée pour la même raison : à 15rem, le
 * tiroir laisse tout le flanc droit de l'arène libre, en paysage comme en portrait.
 */
export type AidePanelProps = {
  /** La vue projetée par le serveur : c'est d'elle que sortent les coups possibles. */
  vue: VuePartie;
  /**
   * La raison du dernier coup refusé, telle que le serveur l'a dite (message du moteur, règle
   * comprise). `null` quand rien n'a été refusé. Un changement de cette valeur ouvre le tiroir.
   */
  refus?: string | null;
  /**
   * Vrai pour une **première partie** : le parcours guidé s'affiche, et le tiroir s'ouvre d'emblée.
   * L'appelant décide (partie d'entraînement, mémoire du navigateur) — l'aide ne le devine pas.
   */
  premierePartie?: boolean;
  /**
   * Au bout de combien de temps sans rien faire on propose des coups, en millisecondes.
   *
   * On ne propose rien avant : une suggestion qui arrive tout de suite empêche de réfléchir, et
   * c'est le joueur qui doit trouver. 12 s est le délai retenu — assez pour lire son plateau,
   * assez court pour ne pas rester bloqué.
   */
  delaiSuggestionMs?: number;
};

/** Les onglets du tiroir. L'aide d'un refus n'en est pas un : elle s'affiche en tête, quand il y en a. */
type Onglet = "coups" | "guide" | "mots";

const ONGLETS: { cle: Onglet; libelle: string }[] = [
  { cle: "coups", libelle: "Que puis-je faire ?" },
  { cle: "guide", libelle: "Partie guidée" },
  { cle: "mots", libelle: "Les mots du jeu" },
];

export function AidePanel({
  vue,
  refus = null,
  premierePartie = false,
  delaiSuggestionMs = 12_000,
}: AidePanelProps) {
  const [ouvert, setOuvert] = useState(premierePartie);
  const [onglet, setOnglet] = useState<Onglet>(premierePartie ? "guide" : "coups");
  const [hesite, setHesite] = useState(false);
  // L'étape de guide déjà atteinte : mémorisée pour que le parcours ne recule jamais (voir `guide.ts`).
  const [etapeAtteinte, setEtapeAtteinte] = useState(0);
  const [motOuvert, setMotOuvert] = useState<string | null>(null);

  const monTour = estMonTour(vue);
  const coups = useMemo(() => suggestions(vue), [vue]);
  const refusExplique = useMemo(() => (refus ? expliquerRefus(refus) : null), [refus]);

  const progression = useMemo(() => avancerGuide(vue, etapeSure(etapeAtteinte)), [
    vue,
    etapeAtteinte,
  ]);

  // La progression constatée se mémorise : c'est ce qui empêche le guide de revenir en arrière
  // quand l'état du plateau change après coup (Actif adverse remplacé, évolution…).
  useEffect(() => {
    if (progression.index > etapeAtteinte) setEtapeAtteinte(progression.index);
  }, [progression.index, etapeAtteinte]);

  // Un coup refusé ouvre le tiroir : l'explication doit venir au joueur, pas l'attendre.
  useEffect(() => {
    if (refus) setOuvert(true);
  }, [refus]);

  // « Hésiter », c'est rester sans rien faire alors que c'est à soi de jouer. Le minuteur repart à
  // chaque changement de plateau (un coup joué, un coup de l'adversaire) : il mesure bien l'attente
  // du joueur, pas l'âge de la page. Hors de son tour, personne n'hésite — on n'affiche rien.
  const signature = `${vue.tour.numero}:${vue.tour.phase}:${coups.length}:${monTour}`;
  useEffect(() => {
    setHesite(false);
    if (!monTour || vue.terminee || coups.length === 0) return;
    const minuteur = setTimeout(() => setHesite(true), delaiSuggestionMs);
    return () => clearTimeout(minuteur);
  }, [signature, monTour, vue.terminee, coups.length, delaiSuggestionMs]);

  const alerte = refusExplique !== null || (hesite && !ouvert);

  return (
    // Hors flux (`fixed`) : le tiroir n'allonge jamais la page du plateau. `pointer-events-none` sur
    // l'enveloppe laisse le plateau cliquable autour ; seul le panneau capte les clics.
    <div className="pointer-events-none fixed inset-x-0 top-0 z-30 flex justify-start px-2 pt-2">
      <section
        data-testid="aide"
        className="pointer-events-auto flex w-[15rem] max-w-[calc(100vw-1rem)] flex-col rounded-2xl border border-[rgba(201,162,39,0.35)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] text-foreground shadow-[0_8px_30px_-12px_rgba(0,0,0,0.8)]"
      >
        <header className="flex items-center justify-between gap-2 px-3 py-2">
          <button
            type="button"
            data-testid="aide-bascule"
            className="flex items-center gap-2 font-heading text-sm font-bold text-gold"
            aria-expanded={ouvert}
            aria-controls="aide-corps"
            onClick={() => setOuvert((o) => !o)}
          >
            <span aria-hidden>{ouvert ? "▾" : "▸"}</span>
            Aide
            {alerte && (
              // Pastille d'appel quand il y a quelque chose à lire sans que le tiroir soit ouvert.
              <span
                data-testid="aide-pastille"
                className="rounded-full bg-[rgba(226,80,59,0.25)] px-2 py-0.5 text-[0.7rem] font-semibold text-[#F2A197]"
              >
                à lire
              </span>
            )}
          </button>
        </header>

        {/* L'objectif reste visible même replié : c'est ce qu'on oublie en premier quand on débute. */}
        <p
          data-testid="aide-objectif"
          className="px-3 pb-2 text-[0.72rem] leading-snug text-muted-foreground"
        >
          {OBJECTIF}
        </p>

        {ouvert && (
          <div id="aide-corps" className="flex max-h-[60vh] flex-col overflow-y-auto px-2 pb-2">
            {/* Le refus passe devant tout le reste : c'est la question que le joueur vient de se poser. */}
            {refusExplique && (
              <div
                data-testid="aide-refus"
                role="status"
                aria-live="polite"
                className="mb-2 rounded-xl border border-[rgba(226,80,59,0.45)] bg-[rgba(226,80,59,0.12)] px-3 py-2"
              >
                <p className="font-heading text-sm font-bold text-[#F2A197]">
                  {refusExplique.explication?.titre ?? "Ce coup n'est pas possible"}
                </p>
                {/* Le message DU MOTEUR, tel quel : le serveur fait autorité sur le pourquoi factuel. */}
                <p className="mt-1 text-xs text-muted-foreground">{refusExplique.message}</p>
                {refusExplique.explication && (
                  <>
                    <p className="mt-1 text-xs leading-snug">
                      {refusExplique.explication.explication}
                    </p>
                    <p
                      data-testid="aide-alternative"
                      className="mt-1 text-xs font-semibold leading-snug text-[#7FE3B0]"
                    >
                      {refusExplique.explication.alternative}
                    </p>
                  </>
                )}
              </div>
            )}

            <div className="mb-2 flex flex-wrap gap-1" role="tablist" aria-label="Aide du jeu">
              {ONGLETS.map((o) => (
                <button
                  key={o.cle}
                  type="button"
                  role="tab"
                  aria-selected={onglet === o.cle}
                  data-testid={`aide-onglet-${o.cle}`}
                  onClick={() => setOnglet(o.cle)}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[0.7rem] font-semibold transition-opacity",
                    "bg-[rgba(201,162,39,0.22)] text-gold",
                    onglet !== o.cle && "opacity-40",
                  )}
                >
                  {o.libelle}
                </button>
              ))}
            </div>

            {onglet === "coups" && <Coups coups={coups} monTour={monTour} />}
            {onglet === "guide" && <Guide progression={progression} />}
            {onglet === "mots" && (
              <Mots ouvert={motOuvert} onChoisir={(m) => setMotOuvert((p) => (p === m ? null : m))} />
            )}
          </div>
        )}

        {/* Replié, mais le joueur hésite : on l'appelle sans ouvrir le tiroir par-dessus son plateau. */}
        {!ouvert && hesite && (
          <p
            data-testid="aide-hesitation"
            role="status"
            aria-live="polite"
            className="px-3 pb-2 text-xs leading-snug text-[#7FE3B0]"
          >
            {"Tu hésites ? Ouvre l'aide : "}
            {coups.length} coup{coups.length > 1 ? "s" : ""} te sont proposés.
          </p>
        )}
      </section>
    </div>
  );
}

/** Borne défensive de l'étape mémorisée : un index négatif ou non fini ramène au début du parcours. */
function etapeSure(index: number): number {
  return Number.isFinite(index) && index > 0 ? index : 0;
}

/**
 * Les coups possibles, mis en mots.
 *
 * Ce sont des **lignes de texte**, pas des boutons : rien n'est cliquable ici, donc l'aide ne peut
 * pas jouer à la place du joueur. Il lit, puis il joue lui-même dans la barre d'actions.
 */
function Coups({
  coups,
  monTour,
}: {
  coups: ReturnType<typeof suggestions>;
  monTour: boolean;
}) {
  if (!monTour) {
    return (
      <p data-testid="aide-coups-vide" className="px-2 py-2 text-xs italic text-muted-foreground">
        {"C'est à l'adversaire de jouer. Profites-en pour regarder son plateau."}
      </p>
    );
  }
  if (coups.length === 0) {
    return (
      <p data-testid="aide-coups-vide" className="px-2 py-2 text-xs italic text-muted-foreground">
        {"Aucun coup à proposer pour l'instant."}
      </p>
    );
  }
  return (
    <ul data-testid="aide-coups" className="flex flex-col gap-1">
      {coups.map((c) => (
        <li
          key={`${c.type}-${c.etiquette}`}
          data-testid={`aide-coup-${c.type}`}
          className="rounded-xl bg-[rgba(157,0,255,0.12)] px-3 py-2"
        >
          <p className="text-xs font-semibold">{c.etiquette}</p>
          <p className="mt-0.5 text-[0.7rem] leading-snug text-muted-foreground">{c.pourquoi}</p>
        </li>
      ))}
    </ul>
  );
}

/** Le parcours guidé : l'étape en cours, et le chemin parcouru. */
function Guide({ progression }: { progression: ReturnType<typeof avancerGuide> }) {
  if (progression.termine) {
    return (
      <p data-testid="aide-guide-fini" className="px-2 py-2 text-xs leading-snug">
        Tu as fait le tour : poser, attacher une énergie, attaquer, prendre une récompense. Tu sais
        jouer — à toi de gagner les cinq récompenses qui restent.
      </p>
    );
  }
  const { etape, index } = progression;
  if (!etape) return null;
  const regleExpliquee = EXPLICATIONS[etape.regle];
  return (
    <div data-testid="aide-guide" className="px-2 py-1">
      <p className="font-mono text-[0.7rem] text-muted-foreground">
        Étape {index + 1} sur {ETAPES_GUIDE.length}
      </p>
      <p className="mt-0.5 font-heading text-sm font-bold text-gold">{etape.titre}</p>
      <p data-testid="aide-guide-consigne" className="mt-1 text-xs leading-snug">
        {etape.consigne}
      </p>
      {/* La règle enseignée, expliquée : le guide apprend la règle, il ne fait pas que donner un ordre. */}
      {regleExpliquee && (
        <p className="mt-1 text-[0.7rem] leading-snug text-muted-foreground">
          {regleExpliquee.explication}
        </p>
      )}
    </div>
  );
}

/** Le glossaire : la liste des mots, et la définition de celui qu'on ouvre. */
function Mots({
  ouvert,
  onChoisir,
}: {
  ouvert: string | null;
  onChoisir: (mot: string) => void;
}) {
  return (
    <div data-testid="aide-mots">
      <div className="flex flex-wrap gap-1">
        {Object.keys(GLOSSAIRE).map((mot) => (
          <button
            key={mot}
            type="button"
            data-testid={`aide-mot-${mot}`}
            aria-expanded={ouvert === mot}
            onClick={() => onChoisir(mot)}
            className={cn(
              "rounded-full border border-[rgba(201,162,39,0.35)] px-2 py-0.5 text-[0.7rem]",
              ouvert === mot && "bg-[rgba(201,162,39,0.22)] text-gold",
            )}
          >
            {mot}
          </button>
        ))}
      </div>
      {ouvert && (
        <p
          data-testid="aide-mot-definition"
          className="mt-2 rounded-xl bg-[rgba(201,162,39,0.1)] px-3 py-2 text-xs leading-snug"
        >
          <strong className="text-gold">{ouvert}</strong> — {GLOSSAIRE[ouvert]}
        </p>
      )}
    </div>
  );
}
