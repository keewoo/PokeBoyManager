"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";
import type { CategorieLigne, LigneJournal } from "@/lib/game/journal";

/**
 * Le **journal de partie** (lot `j-plateau-journal`) : le fil des coups en français, relié au plateau.
 *
 * Il affiche les lignes déjà traduites par `construireJournal` (le serveur fait autorité, l'écran ne
 * rejoue aucune règle). Trois exigences du lot y vivent :
 *
 * - **tout coup se lit en français** (jamais un `event_type` brut — la traduction est garantie par le
 *   registre et son test de parité) ; le **dernier coup est mis en évidence** ;
 * - **le calcul des dégâts est consultable** : chaque attaque porte un détail (R-10.9) qu'on déplie ;
 * - les **effets automatiques** (poison entre les tours, expiration d'un effet) apparaissent, et un
 *   filtre permet de les isoler — comme « mes coups » et « ceux de l'adversaire ».
 *
 * Reliure journal ↔ plateau : survoler (ou focaliser) une ligne remonte au parent l'`instance_id` du
 * Pokémon concerné (`onSurvol`), que le plateau met alors en évidence.
 *
 * **Tiroir escamotable en position fixe** : le plateau occupe tout l'écran d'un téléphone (critère
 * « toutes les zones sans défilement », lot `j-plateau-layout`). Le journal est donc un tiroir **hors
 * du flux** (`fixed`), **replié par défaut** pour ne masquer ni la main ni l'actif — on l'ouvre quand
 * on veut relire ; ouvert, il recouvre le bas de l'écran avec son propre défilement interne, sans
 * jamais allonger la page.
 */
export type JournalPanelProps = {
  lignes: LigneJournal[];
  /**
   * Remonte l'`instance_id` à mettre en évidence sur le plateau quand une ligne est survolée/focalisée
   * (`null` au survol sortant). Absent → le journal reste un simple fil, sans reliure visuelle.
   */
  onSurvol?: (surligne: string | null) => void;
};

/** Libellé court et style d'une catégorie de ligne, pour la pastille et les filtres. */
const CATEGORIES: Record<CategorieLigne, { court: string; filtre: string; classe: string }> = {
  moi: { court: "Toi", filtre: "Mes coups", classe: "bg-[rgba(127,227,176,0.22)] text-[#7FE3B0]" },
  adversaire: { court: "Adv.", filtre: "Adversaire", classe: "bg-[rgba(226,80,59,0.22)] text-[#F2A197]" },
  auto: { court: "Auto", filtre: "Effets auto", classe: "bg-[rgba(201,162,39,0.22)] text-gold" },
};

const ORDRE_FILTRES: CategorieLigne[] = ["moi", "adversaire", "auto"];

/**
 * Rend le tiroir : en-tête repliable, filtres par catégorie (actifs par défaut), et la liste du plus
 * récent au plus ancien (dernier coup mis en évidence, détail des dégâts dépliable, ligne non traduite
 * toujours visible). Survoler/focaliser une ligne remonte son `instance_id` au plateau via `onSurvol`.
 */
export function JournalPanel({ lignes, onSurvol }: JournalPanelProps) {
  // Replié par défaut : sur le plateau plein écran, on n'ouvre le tiroir que pour relire.
  const [ouvert, setOuvert] = useState(false);
  // Filtres indépendants : tous actifs au départ (on voit tout le fil).
  const [filtres, setFiltres] = useState<Record<CategorieLigne, boolean>>({
    moi: true,
    adversaire: true,
    auto: true,
  });
  // Détail du calcul des dégâts déplié, par clé de ligne (consultable à la demande).
  const [detailsOuverts, setDetailsOuverts] = useState<Record<string, boolean>>({});

  // La ligne la plus récente (dernier événement du dernier coup) : mise en évidence.
  const cleDerniere = lignes.at(-1)?.cle ?? null;

  // On affiche du plus récent au plus ancien : le dernier coup est en tête, visible sans défiler.
  // Une ligne non traduite est TOUJOURS montrée (un bug ne se cache pas derrière un filtre).
  const visibles = [...lignes].reverse().filter((l) => !l.traduit || filtres[l.categorie]);

  function basculerFiltre(cle: CategorieLigne) {
    setFiltres((f) => ({ ...f, [cle]: !f[cle] }));
  }

  function basculerDetail(cle: string) {
    setDetailsOuverts((d) => ({ ...d, [cle]: !d[cle] }));
  }

  return (
    // Hors flux (`fixed`) : le tiroir n'allonge jamais la page du plateau. `pointer-events-none` sur
    // l'enveloppe laisse le plateau cliquable autour ; seul le panneau capte les clics.
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-2 pb-2">
      <section
        data-testid="journal"
        className="pointer-events-auto flex w-full max-w-3xl flex-col rounded-2xl border border-[rgba(157,0,255,0.35)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] text-foreground shadow-[0_-8px_30px_-12px_rgba(0,0,0,0.8)]"
      >
        <header className="flex items-center justify-between gap-2 px-3 py-2">
          <button
            type="button"
            className="flex items-center gap-2 font-heading text-sm font-bold text-gold"
            aria-expanded={ouvert}
            aria-controls="journal-corps"
            onClick={() => setOuvert((o) => !o)}
          >
            <span aria-hidden>{ouvert ? "▾" : "▸"}</span>
            Journal
            <span className="font-mono text-xs text-muted-foreground">({lignes.length})</span>
          </button>

          {ouvert && (
            <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Filtres du journal">
              {ORDRE_FILTRES.map((cle) => (
                <button
                  key={cle}
                  type="button"
                  aria-pressed={filtres[cle]}
                  data-testid={`filtre-${cle}`}
                  onClick={() => basculerFiltre(cle)}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[0.7rem] font-semibold transition-opacity",
                    CATEGORIES[cle].classe,
                    !filtres[cle] && "opacity-35",
                  )}
                >
                  {CATEGORIES[cle].filtre}
                </button>
              ))}
            </div>
          )}
        </header>

        {ouvert && (
          <ol
            id="journal-corps"
            data-testid="journal-liste"
            className="max-h-[55vh] overflow-y-auto px-2 pb-2"
          >
            {visibles.length === 0 ? (
              <li className="px-2 py-3 text-sm italic text-muted-foreground">
                {lignes.length === 0 ? "La partie commence." : "Aucun coup pour ce filtre."}
              </li>
            ) : (
              visibles.map((ligne) => {
                const cat = CATEGORIES[ligne.categorie];
                const estDerniere = ligne.cle === cleDerniere;
                const detailVisible = !!detailsOuverts[ligne.cle];
                return (
                  <li
                    key={ligne.cle}
                    data-testid="ligne-journal"
                    data-categorie={ligne.categorie}
                    data-derniere={estDerniere ? "" : undefined}
                    data-traduit={ligne.traduit ? "" : "non"}
                    tabIndex={ligne.surligne ? 0 : undefined}
                    className={cn(
                      "rounded-lg px-2 py-1.5 text-sm leading-snug",
                      ligne.surligne &&
                        "cursor-help hover:bg-[rgba(255,255,255,0.06)] focus:bg-[rgba(255,255,255,0.06)] focus:outline-none",
                      estDerniere && "bg-[rgba(242,193,78,0.12)] ring-1 ring-gold/50",
                      !ligne.traduit && "bg-[rgba(226,59,59,0.14)] text-[#F2A197]",
                    )}
                    onMouseEnter={ligne.surligne ? () => onSurvol?.(ligne.surligne) : undefined}
                    onMouseLeave={ligne.surligne ? () => onSurvol?.(null) : undefined}
                    onFocus={ligne.surligne ? () => onSurvol?.(ligne.surligne) : undefined}
                    onBlur={ligne.surligne ? () => onSurvol?.(null) : undefined}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={cn("mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[0.65rem] font-semibold", cat.classe)}
                        aria-hidden
                      >
                        {cat.court}
                      </span>
                      <span className="min-w-0 flex-1">
                        {ligne.texte}
                        {ligne.detailDegats && (
                          <button
                            type="button"
                            data-testid="detail-degats-bouton"
                            aria-expanded={detailVisible}
                            onClick={() => basculerDetail(ligne.cle)}
                            className="ml-2 rounded border border-gold/40 px-1.5 py-0.5 text-[0.65rem] font-semibold text-gold hover:bg-gold/10"
                          >
                            {detailVisible ? "masquer le détail" : "détail"}
                          </button>
                        )}
                        {ligne.detailDegats && detailVisible && (
                          <span
                            data-testid="detail-degats"
                            className="mt-1 block rounded bg-[rgba(0,0,0,0.35)] px-2 py-1 font-mono text-xs text-[#EAF3EE]"
                          >
                            {ligne.detailDegats}
                          </span>
                        )}
                      </span>
                      <span className="shrink-0 font-mono text-[0.65rem] text-muted-foreground" aria-hidden>
                        #{ligne.numero}
                      </span>
                    </div>
                  </li>
                );
              })
            )}
          </ol>
        )}
      </section>
    </div>
  );
}
