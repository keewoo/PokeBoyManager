"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Le clavier d'une surcouche de jeu (lot `j-accessibilite-jeu`) : **Échap** ferme, **Tab** reste
 * dedans, et le focus revient d'où il venait.
 *
 * Pourquoi un hook partagé plutôt que trois copies : les quatre surcouches du jeu (fenêtre de
 * décision, écran de fin, consultation d'une zone, carte agrandie) n'avaient **aucune** gestion du
 * clavier. Au clavier seul, une modale ouverte était un cul-de-sac : impossible de la fermer, et le
 * Tab continuait de parcourir le plateau *derrière* elle — on tabulait dans une partie qu'on ne
 * voyait plus. Le critère d'acceptation du lot est qu'une partie complète se joue au clavier seul :
 * il se joue ici.
 *
 * Trois comportements, et ils suivent la pratique établie des boîtes de dialogue :
 *
 * 1. **Échap** appelle `onFermer`. Toujours — même sur une surcouche non modale comme le zoom de
 *    carte : c'est la touche que tout le monde essaie en premier.
 * 2. **Tab** et **Maj+Tab** bouclent sur les éléments focusables de la surcouche (`piege`). Sans
 *    ça, le focus sort par le bas et se perd dans le plateau inaccessible.
 * 3. le **focus** va au premier élément focusable à l'ouverture (ou au conteneur lui-même s'il n'y
 *    en a aucun), et **revient** à l'élément qui l'avait au démontage. Un joueur qui ferme une
 *    fenêtre de décision retrouve son clavier là où il l'avait laissé.
 *
 * @param onFermer  ce que fait Échap. Absent → aucune fermeture au clavier (surcouche obligatoire).
 * @param piege     piéger le Tab dans la surcouche. `false` pour une surcouche qui ne bloque pas le
 *                  jeu derrière (le zoom de carte), où sortir au Tab est le comportement attendu.
 * @param actif     `false` quand la surcouche est repliée (son conteneur n'est pas monté) : rien
 *                  n'est écouté, et le focus est **repris** quand elle se redéploie. C'est ce qui
 *                  permet d'appeler ce crochet depuis un composant qui se replie sans le découper
 *                  en deux — un crochet ne peut pas vivre derrière une condition.
 * @returns la `ref` à poser sur le conteneur de la surcouche.
 */
export function useModale<T extends HTMLElement = HTMLDivElement>({
  onFermer,
  piege = true,
  actif = true,
}: {
  onFermer?: () => void;
  piege?: boolean;
  actif?: boolean;
} = {}) {
  const ref = useRef<T | null>(null);

  const focusables = useCallback((): HTMLElement[] => {
    const racine = ref.current;
    if (!racine) return [];
    const candidats = racine.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    // Un élément masqué ne doit pas recevoir le focus : s'y piéger ressemble exactement à une page
    // figée. On le détecte par le style calculé et `aria-hidden`, et **non** par `offsetParent` :
    // jsdom ne calcule aucune mise en page, donc `offsetParent` y est toujours nul — le filtre
    // aurait vidé la liste dans tous les tests, et la garde n'aurait gardé que le navigateur.
    return Array.from(candidats).filter((el) => {
      if (el.hasAttribute("hidden") || el.getAttribute("aria-hidden") === "true") return false;
      const style = window.getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden";
    });
  }, []);

  // Focus à l'ouverture, restitution à la fermeture.
  useEffect(() => {
    if (!actif) return;
    const precedent = document.activeElement as HTMLElement | null;
    const premier = focusables()[0];
    // ⛔ On ne restitue le focus que si on l'a réellement **pris**. Une surcouche sans aucun
    // contrôle — le zoom de carte — ne le prend pas : le rendre en partant ramènerait le focus sur
    // la carte qu'on vient de quitter, et le Tab suivant la rouvrirait. Mesuré : la tabulation sur
    // le plateau tournait en rond et n'atteignait jamais la barre d'actions (e2e
    // « une partie se joue au clavier seul », qui a trouvé exactement ça).
    if (!premier) return;
    premier.focus();
    return () => {
      // `isConnected` : si l'élément d'origine a disparu avec la page, on ne force rien.
      if (precedent?.isConnected) precedent.focus?.();
    };
  }, [actif, focusables]);

  useEffect(() => {
    if (!actif) return;
    const surTouche = (e: KeyboardEvent) => {
      if (e.key === "Escape" && onFermer) {
        e.stopPropagation();
        onFermer();
        return;
      }
      if (e.key !== "Tab" || !piege) return;
      const liste = focusables();
      const premier = liste[0];
      const dernier = liste.at(-1);
      if (!premier || !dernier) return;
      const actif = document.activeElement;
      // Le bouclage est explicite aux deux bords : on ne laisse jamais le navigateur emmener le
      // focus hors de la surcouche.
      if (!e.shiftKey && actif === dernier) {
        e.preventDefault();
        premier.focus();
      } else if (e.shiftKey && (actif === premier || !ref.current?.contains(actif))) {
        e.preventDefault();
        dernier.focus();
      }
    };
    document.addEventListener("keydown", surTouche);
    return () => document.removeEventListener("keydown", surTouche);
  }, [actif, onFermer, piege, focusables]);

  return ref;
}
