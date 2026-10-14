/**
 * **Contraste** : le calcul WCAG, à un seul endroit du dépôt.
 *
 * Ces fonctions vivaient en copie privée dans `src/__tests__/contraste-jeu.test.ts` (lot
 * `j-accessibilite-jeu`). Le lot `j-arene-decors` en a besoin aussi — un décor d'arène doit se
 * mesurer contre *tous* les repères posés dessus — et deux copies d'une formule, c'est deux
 * occasions de la corriger à moitié. Elles sont donc extraites ici, **exportées et testées**.
 *
 * Ce module ne connaît ni React ni le jeu : il ne manipule que des couleurs.
 */

/** Composantes `0..255` d'une couleur `#rgb` ou `#rrggbb`. */
function composantes(hex: string): [number, number, number] {
  let valeur = hex.trim().replace("#", "");
  if (valeur.length === 3) {
    // Forme courte `#abc` : chaque chiffre vaut son doublement (`#aabbcc`).
    valeur = valeur
      .split("")
      .map((c) => c + c)
      .join("");
  }
  if (!/^[0-9a-fA-F]{6}$/.test(valeur)) {
    // Un repli silencieux donnerait un contraste faux — donc rassurant à tort.
    throw new Error(`couleur illisible : ${hex} (attendu #rgb ou #rrggbb)`);
  }
  return [0, 2, 4].map((i) => parseInt(valeur.slice(i, i + 2), 16)) as [number, number, number];
}

/** Luminance relative d'une couleur `#rrggbb` (formule WCAG 2.x, critère 1.4.3). */
export function luminance(hex: string): number {
  const [r, g, b] = composantes(hex)
    .map((c) => c / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)) as [
    number,
    number,
    number,
  ];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Rapport de contraste entre deux couleurs opaques (1:1 à 21:1). */
export function contraste(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/**
 * Couleur **réellement affichée** quand `dessus` est posé à l'opacité `alpha` sur `dessous`.
 *
 * Indispensable pour mesurer honnêtement le plateau : plusieurs repères y sont semi-transparents
 * (`rgba(255,255,255,0.28)` d'un emplacement vide, `opacity-75` de la ligne du Stade). Mesurer leur
 * couleur nominale contre le fond surestimerait le contraste — c'est-à-dire se rassurer à tort.
 *
 * La composition se fait dans l'espace sRGB (comme le navigateur compose les couches), *puis* la
 * luminance est calculée sur le résultat.
 */
export function composer(dessous: string, dessus: string, alpha: number): string {
  if (alpha < 0 || alpha > 1) throw new Error(`alpha hors bornes : ${alpha}`);
  const bas = composantes(dessous);
  const haut = composantes(dessus);
  const melange = bas.map((v, i) => Math.round(haut[i]! * alpha + v * (1 - alpha)));
  return `#${melange.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/**
 * Mélange deux couleurs opaques comme le ferait `color-mix(in srgb, <a> <part>%, <b>)`.
 *
 * Le CSS dérive la variante **nuit** d'un décor par `color-mix` ; le test de contraste doit
 * mesurer la même couleur que celle qui s'affichera. Cette fonction est donc le miroir exact de
 * cette règle CSS — et c'est volontairement la seule façon de la reproduire ici.
 */
export function melangerSrgb(a: string, b: string, part: number): string {
  if (part < 0 || part > 1) throw new Error(`part hors bornes : ${part}`);
  return composer(b, a, part);
}

/** Seuil AA pour du texte (WCAG 2.2, 1.4.3). Un petit texte sur le plateau, c'est exactement ça. */
export const SEUIL_TEXTE = 4.5;

/**
 * Seuil AA pour un repère **non textuel** (WCAG 2.2, 1.4.11 « Contraste des éléments non
 * textuels ») : le liseré d'un emplacement vide, le jeton d'une récompense, un anneau de focus.
 * Leur rôle est d'être *repérable*, pas d'être *lu* — 3:1 est la mesure prévue pour ça.
 */
export const SEUIL_NON_TEXTUEL = 3;
