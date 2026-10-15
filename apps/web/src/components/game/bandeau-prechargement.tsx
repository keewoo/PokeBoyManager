"use client";

import { useEffect, useRef, useState } from "react";

import {
  ETAT_INITIAL,
  type ChargeurImage,
  type EtatPrechargement,
  pourcentage,
  precharger,
  urlsAPrecharger,
} from "@/lib/game/prechargement";
import type { VuePartie } from "@/lib/game/plateau";

/**
 * La barre de pré-chargement des images d'une partie (lot `j-assets-pipeline`).
 *
 * Elle dit ce qui se passe **pendant la mise en place** : les images des deux camps arrivent, et le
 * joueur voit où ça en est. Trois propriétés, chacune pour une raison :
 *
 * - **honnête** — le compte vient des images réellement arrivées (ou définitivement manquées), pas
 *   d'une minuterie. Une barre qui avance toute seule est un mensonge qui se voit au moment où elle
 *   atteint 100 % alors que l'écran est encore vide ;
 * - **hors flux** (`fixed`) — la page `/jeu/parties/{id}` n'admet **aucun défilement** (e2e
 *   `plateau-responsive`, `docs/jeu/ANIMATIONS.md`). Un bandeau en flux normal décalerait le
 *   plateau et ferait échouer le job e2e, sans qu'aucun test unitaire ne bronche ;
 * - **effacée dès qu'elle n'a plus rien à dire** — elle disparaît à la fin, et n'apparaît pas du
 *   tout quand tout est déjà en cache (le cas d'un F5, grâce à l'empreinte posée côté serveur).
 *
 * `aria-live="polite"` et `role="progressbar"` : annoncée au lecteur d'écran sans l'interrompre,
 * comme la file d'attente du salon (`docs/jeu/ACCESSIBILITE.md`).
 */
export function BandeauPrechargement({
  vue,
  charger,
}: {
  /** La vue autoritaire de la partie. `null` = rien à pré-charger encore. */
  vue: VuePartie | null | undefined;
  /** Chargeur injectable — les tests n'ont pas de réseau, et l'e2e veut pouvoir ralentir. */
  charger?: ChargeurImage;
}) {
  const [etat, setEtat] = useState<EtatPrechargement>(ETAT_INITIAL);
  /** Les URL déjà pré-chargées : une vue qui change (un coup joué) ne relance pas tout. */
  const dejaVues = useRef<Set<string>>(new Set());

  useEffect(() => {
    const urls = urlsAPrecharger(vue).filter((url) => !dejaVues.current.has(url));
    if (urls.length === 0) return;
    urls.forEach((url) => dejaVues.current.add(url));

    let demonte = false;
    void precharger(urls, (avancee) => setEtat(avancee), {
      charger,
      interrompu: () => demonte,
    });
    return () => {
      demonte = true;
    };
  }, [vue, charger]);

  if (etat.total === 0 || etat.termine) return null;

  const pct = pourcentage(etat);
  const restantes = etat.total - etat.chargees - etat.echouees;
  return (
    <div
      data-testid="prechargement-bandeau"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-3 pb-2"
    >
      <div className="flex w-full max-w-sm flex-col gap-1 rounded-lg bg-[rgba(10,8,30,0.82)] px-3 py-2 text-[rgba(255,255,255,0.9)] shadow-lg backdrop-blur-sm">
        <p className="flex items-baseline justify-between text-[0.75rem] leading-tight">
          <span>Préparation des cartes…</span>
          <span data-testid="prechargement-compte" className="tabular-nums">
            {etat.chargees + etat.echouees}/{etat.total}
          </span>
        </p>
        <div
          role="progressbar"
          aria-label="Chargement des images de la partie"
          aria-live="polite"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          aria-valuetext={`${pct} % — ${restantes} image${restantes > 1 ? "s" : ""} restante${
            restantes > 1 ? "s" : ""
          }`}
          data-pourcentage={pct}
          className="h-1.5 overflow-hidden rounded-full bg-[rgba(255,255,255,0.18)]"
        >
          {/* Largeur en ligne : c'est une valeur calculée, pas un palier de style — une classe
              Tailwind par pourcentage n'existe pas, et `w-[x%]` dynamique n'est pas compilé. */}
          <div
            className="h-full rounded-full bg-[rgba(140,200,255,0.9)] transition-[width] duration-200 motion-reduce:transition-none"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
    </div>
  );
}
