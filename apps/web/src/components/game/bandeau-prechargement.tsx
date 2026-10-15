"use client";

import { useEffect, useRef, useState } from "react";

import {
  AVANCEE_INITIALE,
  type AvanceeGlobale,
  type ChargeurImage,
  pourcentageDe,
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
  const [avancee, setAvancee] = useState<AvanceeGlobale>(AVANCEE_INITIALE);
  /** Les URL déjà demandées : une vue qui change (un coup joué) ne relance pas tout. */
  const dejaVues = useRef<Set<string>>(new Set());
  /** Le cumul **sur toute la partie**, et pas sur le dernier lot — voir l'avertissement ci-dessous. */
  const cumul = useRef({ total: 0, faits: 0 });
  /** Faux seulement au démontage : c'est la seule raison d'abandonner un chargement en vol. */
  const monte = useRef(true);
  useEffect(() => () => void (monte.current = false), []);

  useEffect(() => {
    const urls = urlsAPrecharger(vue).filter((url) => !dejaVues.current.has(url));
    if (urls.length === 0) return;
    urls.forEach((url) => dejaVues.current.add(url));
    cumul.current.total += urls.length;

    // ⚠️ `interrompu` ne regarde QUE le démontage, jamais le changement de `vue`. La vue de partie
    // est un objet neuf à chaque sondage et à chaque resynchronisation : interrompre ici arrêtait
    // le lot en cours, et comme le lot suivant ne contenait plus aucune URL neuve (toutes déjà
    // dans `dejaVues`), il rendait la main sans rien signaler — la barre restait figée à 40 %
    // pour toujours. Trouvé par l'e2e en 4G, pas par un test unitaire.
    let precedent = 0;
    void precharger(
      urls,
      (lot) => {
        // Le lot rend des compteurs qui lui sont propres : on n'en prend que le **delta**, sinon
        // un second lot ferait reculer la barre.
        const faits = lot.chargees + lot.echouees;
        cumul.current.faits += faits - precedent;
        precedent = faits;
        if (monte.current) setAvancee({ ...cumul.current });
      },
      { charger, interrompu: () => !monte.current },
    );
  }, [vue, charger]);

  const restantes = avancee.total - avancee.faits;
  if (avancee.total === 0 || restantes <= 0) return null;

  const pct = pourcentageDe(avancee.faits, avancee.total);
  return (
    <div
      data-testid="prechargement-bandeau"
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center px-3 pb-2"
    >
      <div className="flex w-full max-w-sm flex-col gap-1 rounded-lg bg-[rgba(10,8,30,0.82)] px-3 py-2 text-[rgba(255,255,255,0.9)] shadow-lg backdrop-blur-sm">
        <p className="flex items-baseline justify-between text-[0.75rem] leading-tight">
          <span>Préparation des cartes…</span>
          <span data-testid="prechargement-compte" className="tabular-nums">
            {avancee.faits}/{avancee.total}
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
