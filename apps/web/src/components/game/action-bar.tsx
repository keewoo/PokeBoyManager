"use client";

import { cn } from "@/lib/utils";
import type { Selection } from "@/lib/game/interactions";
import type { VueActionLegale, VueActionRefusee } from "@/lib/game/plateau";

/**
 * La **barre d'actions** d'une partie (lot `j-plateau-interactions`) : ce que le joueur peut jouer,
 * ce qui lui est refusé (et pourquoi), et la confirmation d'un coup irréversible.
 *
 * Elle n'ajoute **aucune règle** : elle affiche `actions_legales` et `actions_refusees` tels que le
 * serveur les a produits. Un coup refusé montre la **raison du moteur** (règle citée) au survol, pas
 * un message générique. Un coup ciblé est aussi **glissable** (glisser-déposer) vers une cible
 * illuminée ; un simple tap sur le coup puis sur la cible fait la même chose (tap-tap).
 */
export type ActionBarProps = {
  legales: VueActionLegale[];
  refusees: VueActionRefusee[];
  /** L'étape courante de préparation d'un coup (repos / ciblage / confirmation). */
  selection: Selection;
  /** Un coup est en vol : tout est désactivé (anti double-envoi, avec l'idempotence serveur). */
  verrou: boolean;
  onChoisir: (action: VueActionLegale) => void;
  onConfirmer: () => void;
  onAnnuler: () => void;
};

const BTN =
  "rounded-lg border px-3 py-1.5 text-sm font-semibold transition-colors disabled:opacity-50 " +
  "disabled:cursor-not-allowed";
const BTN_ACTION =
  BTN + " border-[rgba(242,193,78,0.5)] bg-[rgba(242,193,78,0.14)] text-gold hover:bg-[rgba(242,193,78,0.26)]";
const BTN_DANGER =
  BTN + " border-[rgba(226,59,59,0.6)] bg-[rgba(226,59,59,0.16)] text-[#ffb4b4] hover:bg-[rgba(226,59,59,0.28)]";
const BTN_NEUTRE =
  BTN + " border-[rgba(255,255,255,0.25)] bg-transparent text-muted-foreground hover:bg-[rgba(255,255,255,0.08)]";
const BTN_REFUS =
  BTN + " cursor-not-allowed border-dashed border-[rgba(255,255,255,0.2)] bg-transparent text-muted-foreground";

const BARRE = "flex flex-wrap items-center justify-center gap-2 px-2 py-1";

export function ActionBar({
  legales,
  refusees,
  selection,
  verrou,
  onChoisir,
  onConfirmer,
  onAnnuler,
}: ActionBarProps) {
  // Confirmation d'un coup irréversible : on ne valide que sur un « oui » explicite (R-5.7 / R-14.3).
  if (selection.phase === "confirmation") {
    return (
      <div data-testid="confirmation" role="group" aria-label="Confirmer le coup" className={BARRE}>
        <span className="text-sm">
          Confirmer : <strong className="text-gold">{selection.action.etiquette}</strong> ?
        </span>
        <button type="button" data-testid="confirmer" disabled={verrou} onClick={onConfirmer} className={BTN_DANGER}>
          Confirmer
        </button>
        <button type="button" data-testid="annuler" disabled={verrou} onClick={onAnnuler} className={BTN_NEUTRE}>
          Annuler
        </button>
      </div>
    );
  }

  // Ciblage : les cibles valides sont illuminées sur le plateau ; on peut encore annuler.
  if (selection.phase === "cible") {
    return (
      <div data-testid="ciblage" role="group" aria-label="Choisir une cible" className={BARRE}>
        <span className="text-sm">
          Choisis une cible pour «&nbsp;<strong className="text-gold">{selection.action.etiquette}</strong>&nbsp;».
        </span>
        <button type="button" data-testid="annuler" disabled={verrou} onClick={onAnnuler} className={BTN_NEUTRE}>
          Annuler
        </button>
      </div>
    );
  }

  // Repos : les coups jouables (certains glissables), puis les coups refusés, grisés avec leur raison.
  return (
    <div data-testid="barre-actions" role="group" aria-label="Actions possibles" className={BARRE}>
      {legales.length === 0 && refusees.length === 0 && (
        <span className="text-sm italic text-muted-foreground">Aucune action pour l&apos;instant.</span>
      )}
      {legales.map((action) => {
        const ciblee = action.cibles.length > 0;
        return (
          <button
            key={`${action.type}:${action.etiquette}`}
            type="button"
            data-testid={`action-${action.type}`}
            disabled={verrou}
            draggable={ciblee && !verrou}
            onDragStart={
              ciblee
                ? (e) => {
                    e.dataTransfer.setData("text/plain", action.type);
                    onChoisir(action);
                  }
                : undefined
            }
            onClick={() => onChoisir(action)}
            title={
              ciblee
                ? "Touche ce coup puis une cible, ou glisse-le sur une cible"
                : action.etiquette
            }
            className={cn(action.irreversible ? BTN_DANGER : BTN_ACTION)}
          >
            {action.etiquette}
          </button>
        );
      })}
      {refusees.map((refus) => (
        <button
          key={`${refus.type}:${refus.etiquette}`}
          type="button"
          data-testid={`refus-${refus.type}`}
          disabled
          aria-disabled="true"
          title={`${refus.etiquette} — impossible : ${refus.message} (${refus.regle})`}
          aria-label={`${refus.etiquette} — impossible : ${refus.message} (${refus.regle})`}
          className={BTN_REFUS}
        >
          <span aria-hidden>🔒</span> {refus.etiquette}
        </button>
      ))}
    </div>
  );
}
