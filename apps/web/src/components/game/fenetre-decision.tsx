"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import {
  NON,
  OUI,
  choixParDefaut,
  deplacer,
  filtrerOptions,
  reponseValide,
  typesPresents,
} from "@/lib/game/decision";
import { formatSecondes } from "@/lib/game/horloges";
import type { VueDemande, VueOptionCarte, VuePartie } from "@/lib/game/plateau";

/**
 * Fenêtre de décision générique (lot `j-plateau-decisions`) : **un** composant piloté par la
 * `VueDemande` que le serveur pose dans l'état, jamais un écran par carte (le nombre de cartes rend
 * cette approche impossible dès la deuxième extension). Elle sait rendre les six catégories de
 * demande — choisir une ou plusieurs cartes, ordonner, oui/non, un type, un nombre — à partir de la
 * seule description de la demande.
 *
 * Deux regards, car une demande est **publique** (les deux joueurs voient la partie en pause, jamais
 * d'écran muet) :
 *
 * - c'est **à moi** de décider (`destinataire === vue.pour`) → une boîte de dialogue modale où je
 *   choisis, où je peux **annuler avant de valider**, et qui montre le **temps restant** et **ce qui
 *   se passera à l'expiration** (la réponse par défaut, miroir du moteur) ;
 * - c'est à l'**adversaire** de décider → une bannière qui dit clairement que j'attends, pourquoi,
 *   et jusqu'à quand.
 *
 * L'interface ne décide de rien : elle propose ce que la demande autorise et **soumet** le choix ;
 * le serveur rejoue et valide la réponse (`repondre_demande`). La fenêtre est hors flux de page
 * (`fixed`) pour ne pas introduire de défilement sur le plateau (l'e2e du plateau l'interdit).
 */
export type FenetreDecisionProps = {
  vue: VuePartie;
  /**
   * Soumet la réponse du destinataire : l'identifiant de la demande et la liste des options retenues
   * (liste vide = abandon d'un effet facultatif). Doit **rejeter** sur un refus serveur (`ApiError`
   * 422) dont le message porte la raison du moteur : la fenêtre l'affiche telle quelle. Absent → la
   * fenêtre reste informative (aucune soumission possible).
   */
  onRepondre?: (demandeId: string, choix: string[]) => Promise<void>;
  /** Horloge injectable (ms) — pour les tests. Par défaut `Date.now`. */
  maintenant?: () => number;
};

/**
 * Le temps restant estimé localement d'une demande chronométrée, rafraîchi deux fois par seconde.
 *
 * Le serveur fait autorité : il décompte et expire la demande (action `expirer_demande`). Le client
 * n'en fait qu'une estimation entre deux messages — il retranche le temps écoulé **localement** depuis
 * la réception (`cle`/`tempsRestant` changent → on recale), exactement comme les horloges de partie.
 * On n'auto-soumet jamais à zéro : c'est le serveur qui applique la réponse par défaut.
 */
function useRestant(cle: string | null, tempsRestant: number | null, horloge: () => number): number | null {
  const [recu, setRecu] = useState(() => horloge());
  const [, setTick] = useState(0);
  const horlogeRef = useRef(horloge);
  horlogeRef.current = horloge;
  useEffect(() => {
    setRecu(horlogeRef.current());
    if (tempsRestant === null) return;
    const t = setInterval(() => setTick((x) => x + 1), 500);
    return () => clearInterval(t);
  }, [cle, tempsRestant]);
  if (tempsRestant === null) return null;
  return Math.max(0, tempsRestant - (horlogeRef.current() - recu));
}

/** Le libellé lisible d'une option : son nom de carte si on le connaît, sinon l'identifiant brut. */
function libelleOption(demande: VueDemande, id: string): string {
  if (id === OUI) return "Oui";
  if (id === NON) return "Non";
  const carte = demande.options_cartes?.find((o) => o.id === id);
  return carte ? carte.nom : id;
}

/** La phrase décrivant ce qui se jouera à l'expiration du délai (réponse par défaut, nommée). */
function phraseDefaut(demande: VueDemande): string {
  if (!demande.obligatoire) return "cette carte est ignorée (tu passes)";
  const ids = choixParDefaut(demande);
  if (ids.length === 0) return "cette carte est ignorée";
  return ids.map((id) => libelleOption(demande, id)).join(", ");
}

/** Pastille de type (code d'élément), doublée du texte — lisible même sans la couleur (daltonisme). */
function PastilleType({ type }: { type: string | null | undefined }) {
  if (!type) return null;
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[0.7rem] font-semibold uppercase text-muted-foreground">
      {type}
    </span>
  );
}

/** Compte à rebours de la décision + réponse par défaut à l'expiration (toujours visibles). */
function Compteur({ demande, restantMs }: { demande: VueDemande; restantMs: number | null }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
      {restantMs !== null && (
        <span data-testid="decision-compteur" className="font-mono font-semibold text-foreground">
          ⏱ {formatSecondes(restantMs / 1000)}
        </span>
      )}
      <span data-testid="decision-defaut">À défaut de réponse : {phraseDefaut(demande)}.</span>
    </div>
  );
}

/** Sélecteur de cartes (catégories « carte » et « cartes ») : recherche, filtres par type, et choix
 * d'entre `minimum` et `maximum` cartes. C'est ce qui rend une pioche de soixante cartes fouillable. */
function SelecteurCartes({
  options,
  selection,
  max,
  onToggle,
}: {
  options: VueOptionCarte[];
  selection: string[];
  max: number;
  onToggle: (id: string) => void;
}) {
  const [requete, setRequete] = useState("");
  const [type, setType] = useState<string | null>(null);
  const types = useMemo(() => typesPresents(options), [options]);
  const visibles = useMemo(() => filtrerOptions(options, requete, type), [options, requete, type]);
  // Plein = on a atteint le maximum. Pour un choix UNIQUE (max 1), on ne grise pas les autres :
  // cliquer une autre carte **remplace** la sélection (plus naturel que de devoir d'abord décocher).
  const bloque = selection.length >= max && max > 1;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={requete}
          onChange={(e) => setRequete(e.target.value)}
          placeholder="Chercher une carte…"
          aria-label="Chercher une carte"
          data-testid="decision-recherche"
          className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
        />
        {types.length > 0 && (
          <div className="flex flex-wrap gap-1" role="group" aria-label="Filtrer par type">
            <button
              type="button"
              data-testid="type-tous"
              aria-pressed={type === null}
              onClick={() => setType(null)}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-semibold",
                type === null ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
              )}
            >
              Tous
            </button>
            {types.map((t) => (
              <button
                key={t}
                type="button"
                data-testid={`type-${t}`}
                aria-pressed={type === t}
                onClick={() => setType(type === t ? null : t)}
                className={cn(
                  "rounded-full px-2.5 py-1 text-xs font-semibold uppercase",
                  type === t ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                )}
              >
                {t}
              </button>
            ))}
          </div>
        )}
      </div>

      <ul
        data-testid="decision-liste"
        className="grid max-h-[40vh] grid-cols-1 gap-1.5 overflow-y-auto sm:grid-cols-2"
      >
        {visibles.map((o) => {
          const choisi = selection.includes(o.id);
          return (
            <li key={o.id}>
              <button
                type="button"
                data-testid={`option-${o.id}`}
                data-choisi={choisi ? "oui" : "non"}
                aria-pressed={choisi}
                disabled={!choisi && bloque}
                onClick={() => onToggle(o.id)}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm",
                  choisi ? "border-primary bg-primary/15 font-semibold" : "border-border bg-background",
                  !choisi && bloque && "cursor-not-allowed opacity-40",
                )}
              >
                <span className="min-w-0 truncate">{o.nom}</span>
                <PastilleType type={o.type} />
              </button>
            </li>
          );
        })}
        {visibles.length === 0 && (
          <li className="col-span-full py-6 text-center text-sm text-muted-foreground">
            Aucune carte ne correspond à ta recherche.
          </li>
        )}
      </ul>
    </div>
  );
}

/** Sélecteur d'ordre (catégorie « ordre ») : la liste complète, réordonnée par « monter / descendre ».
 * La réponse est la permutation courante — pas de filtre ici, l'ordre de toutes les cartes compte. */
function SelecteurOrdre({
  options,
  ordre,
  onDeplacer,
}: {
  options: VueOptionCarte[];
  ordre: string[];
  onDeplacer: (de: number, vers: number) => void;
}) {
  const parId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options]);
  return (
    <ol data-testid="decision-ordre" className="space-y-1.5">
      {ordre.map((id, i) => {
        const carte = parId.get(id);
        return (
          <li
            key={id}
            data-testid={`ordre-${id}`}
            className="flex items-center justify-between gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="font-mono text-muted-foreground">{i + 1}.</span>
              <span className="min-w-0 truncate">{carte ? carte.nom : id}</span>
            </span>
            <span className="flex items-center gap-1">
              <PastilleType type={carte?.type} />
              <button
                type="button"
                data-testid={`ordre-monter-${id}`}
                aria-label={`Monter ${carte ? carte.nom : id}`}
                disabled={i === 0}
                onClick={() => onDeplacer(i, i - 1)}
                className="rounded px-2 py-1 text-base disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                data-testid={`ordre-descendre-${id}`}
                aria-label={`Descendre ${carte ? carte.nom : id}`}
                disabled={i === ordre.length - 1}
                onClick={() => onDeplacer(i, i + 1)}
                className="rounded px-2 py-1 text-base disabled:opacity-30"
              >
                ↓
              </button>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Choix binaire oui/non — deux grands boutons, le choix courant mis en évidence. */
function SelecteurOuiNon({ valeur, onChoisir }: { valeur: string | null; onChoisir: (v: string) => void }) {
  return (
    <div className="flex gap-3" role="group" aria-label="Oui ou non">
      {[OUI, NON].map((v) => (
        <button
          key={v}
          type="button"
          data-testid={`option-${v}`}
          aria-pressed={valeur === v}
          onClick={() => onChoisir(v)}
          className={cn(
            "flex-1 rounded-lg border px-4 py-3 text-base font-semibold",
            valeur === v ? "border-primary bg-primary/15" : "border-border bg-background",
          )}
        >
          {v === OUI ? "Oui" : "Non"}
        </button>
      ))}
    </div>
  );
}

/** Choix d'un type (catégorie « type ») : une puce par option, le choix courant mis en évidence. */
function SelecteurType({
  options,
  valeur,
  onChoisir,
}: {
  options: string[];
  valeur: string | null;
  onChoisir: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Choisir un type">
      {options.map((t) => (
        <button
          key={t}
          type="button"
          data-testid={`option-${t}`}
          aria-pressed={valeur === t}
          onClick={() => onChoisir(t)}
          className={cn(
            "rounded-full border px-3 py-1.5 text-sm font-semibold uppercase",
            valeur === t ? "border-primary bg-primary/15" : "border-border bg-background",
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

/** Choix d'un nombre dans `[minimum, maximum]` : un pas à pas (− / valeur / +), borné. */
function SelecteurNombre({
  valeur,
  min,
  max,
  onChanger,
}: {
  valeur: number;
  min: number;
  max: number;
  onChanger: (n: number) => void;
}) {
  return (
    <div className="flex items-center justify-center gap-4" role="group" aria-label="Choisir un nombre">
      <button
        type="button"
        data-testid="nombre-moins"
        aria-label="Diminuer"
        disabled={valeur <= min}
        onClick={() => onChanger(valeur - 1)}
        className="h-11 w-11 rounded-full border border-border text-2xl disabled:opacity-30"
      >
        −
      </button>
      <span data-testid="nombre-valeur" className="min-w-10 text-center font-mono text-2xl font-bold">
        {valeur}
      </span>
      <button
        type="button"
        data-testid="nombre-plus"
        aria-label="Augmenter"
        disabled={valeur >= max}
        onClick={() => onChanger(valeur + 1)}
        className="h-11 w-11 rounded-full border border-border text-2xl disabled:opacity-30"
      >
        +
      </button>
    </div>
  );
}

/** Bannière d'attente d'une décision adverse : fixe en haut, visible, jamais un écran muet. */
function BanniereAttente({ demande, restantMs }: { demande: VueDemande; restantMs: number | null }) {
  const source = (demande.source?.libelle as string | undefined) ?? "";
  return (
    <div
      data-testid="attente-adverse"
      role="status"
      className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center p-2"
    >
      <div className="flex max-w-xl flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-b-lg bg-card px-4 py-2 text-sm text-card-foreground shadow-lg">
        <span className="font-semibold">⏳ L&apos;adversaire réfléchit</span>
        <span className="opacity-90">
          {source ? `${source} — ` : ""}
          {demande.libelle}
        </span>
        {restantMs !== null && (
          <span data-testid="attente-compteur" className="font-mono">
            {formatSecondes(restantMs / 1000)}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * La modale de décision — **remontée** à chaque nouvelle demande (clé sur `demande.id`) pour repartir
 * d'une sélection vierge, sans effet de réinitialisation. Tient la sélection courante et la soumet.
 */
function ModaleDecision({
  demande,
  moi,
  restantMs,
  onRepondre,
}: {
  demande: VueDemande;
  moi: string;
  restantMs: number | null;
  onRepondre?: (demandeId: string, choix: string[]) => Promise<void>;
}) {
  void moi; // le destinataire a déjà été vérifié par le parent ; gardé pour la lisibilité du contrat
  const cartes = demande.options_cartes ?? [];
  const estCategorieCarte =
    demande.categorie === "carte" || demande.categorie === "cartes" || demande.categorie === "ordre";
  const ensembleCache = estCategorieCarte && cartes.length === 0 && demande.options_nombre != null;

  const [selection, setSelection] = useState<string[]>(() =>
    demande.categorie === "ordre" ? [...(demande.options ?? [])] : [],
  );
  const [nombre, setNombre] = useState<number>(demande.minimum);
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  const choixCourant: string[] = demande.categorie === "nombre" ? [String(nombre)] : selection;
  const peutValider = reponseValide(demande, choixCourant) && !envoi && !ensembleCache;
  const source = (demande.source?.libelle as string | undefined) ?? "";

  const soumettre = useCallback(
    async (choix: string[]) => {
      if (!onRepondre || envoi) return;
      setEnvoi(true);
      setErreur(null);
      try {
        await onRepondre(demande.id, choix);
        // Succès : la vue va changer (demande suivante ou disparue) ; la modale est alors remontée.
      } catch (e) {
        setErreur(
          e instanceof ApiError
            ? e.message
            : "Ta réponse n'a pas pu être envoyée. Réessaie dans un instant.",
        );
        setEnvoi(false);
      }
    },
    [onRepondre, envoi, demande.id],
  );

  const basculerCarte = (id: string) => {
    setSelection((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      const max = demande.categorie === "carte" ? 1 : demande.maximum;
      if (prev.length >= max) return max === 1 ? [id] : prev; // choix unique : on remplace
      return [...prev, id];
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-2 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="decision-titre"
      data-testid="fenetre-decision"
    >
      <div className="flex max-h-[92vh] w-full max-w-lg flex-col gap-3 overflow-hidden rounded-xl bg-card p-4 text-card-foreground shadow-2xl">
        <header className="space-y-1">
          <h2 id="decision-titre" className="text-base font-bold">
            {source ? `${source} — ` : ""}
            {demande.libelle}
          </h2>
          <Compteur demande={demande} restantMs={restantMs} />
        </header>

        {erreur && (
          <p
            role="alert"
            data-testid="decision-erreur"
            className="rounded-md border border-danger/30 bg-danger-background px-3 py-2 text-sm text-danger-foreground"
          >
            {erreur}
          </p>
        )}

        <div className="min-h-0 flex-1 overflow-y-auto">
          {ensembleCache ? (
            <p
              data-testid="decision-ensemble-cache"
              className="py-6 text-center text-sm text-muted-foreground"
            >
              Choix parmi {demande.options_nombre} cartes cachées — la désignation à l&apos;aveugle
              n&apos;est pas encore disponible.
            </p>
          ) : demande.categorie === "oui_non" ? (
            <SelecteurOuiNon valeur={selection[0] ?? null} onChoisir={(v) => setSelection([v])} />
          ) : demande.categorie === "type" ? (
            <SelecteurType
              options={demande.options ?? []}
              valeur={selection[0] ?? null}
              onChoisir={(v) => setSelection([v])}
            />
          ) : demande.categorie === "nombre" ? (
            <SelecteurNombre valeur={nombre} min={demande.minimum} max={demande.maximum} onChanger={setNombre} />
          ) : demande.categorie === "ordre" ? (
            <SelecteurOrdre
              options={cartes}
              ordre={selection}
              onDeplacer={(de, vers) => setSelection((prev) => deplacer(prev, de, vers))}
            />
          ) : (
            <SelecteurCartes
              options={cartes}
              selection={selection}
              max={demande.categorie === "carte" ? 1 : demande.maximum}
              onToggle={basculerCarte}
            />
          )}
        </div>

        <footer className="flex flex-wrap items-center justify-end gap-2">
          {!ensembleCache && selection.length > 0 && demande.categorie !== "ordre" && (
            <button
              type="button"
              data-testid="decision-annuler"
              onClick={() => setSelection([])}
              className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:underline"
            >
              Annuler mon choix
            </button>
          )}
          {!demande.obligatoire && (
            <button
              type="button"
              data-testid="decision-passer"
              disabled={envoi}
              onClick={() => soumettre([])}
              className="rounded-md border border-border px-3 py-2 text-sm font-semibold"
            >
              Passer
            </button>
          )}
          <button
            type="button"
            data-testid="decision-valider"
            disabled={!peutValider}
            onClick={() => soumettre(choixCourant)}
            className={cn(
              "rounded-md px-4 py-2 text-sm font-bold",
              peutValider ? "bg-primary text-primary-foreground" : "cursor-not-allowed bg-muted text-muted-foreground",
            )}
          >
            Valider
          </button>
        </footer>
      </div>
    </div>
  );
}

/**
 * Point d'entrée : lit la demande dans la vue, estime son compte à rebours, et choisit le regard —
 * modale si c'est à moi de décider, bannière d'attente sinon. Rend `null` quand aucune décision n'est
 * en attente. Tous les Hooks sont appelés avant tout retour conditionnel (règle des Hooks).
 */
export function FenetreDecision({ vue, onRepondre, maintenant }: FenetreDecisionProps) {
  const horloge = maintenant ?? (() => Date.now());
  const demande = vue.demande;
  const restantMs = useRestant(demande?.id ?? null, demande?.temps_restant_ms ?? null, horloge);

  if (!demande) return null;
  if (demande.destinataire !== vue.pour) {
    return <BanniereAttente demande={demande} restantMs={restantMs} />;
  }
  return (
    <ModaleDecision
      key={demande.id}
      demande={demande}
      moi={vue.pour}
      restantMs={restantMs}
      onRepondre={onRepondre}
    />
  );
}
