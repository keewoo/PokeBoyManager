import "@testing-library/jest-dom/vitest";

if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

// `localStorage` n'est pas exposé par cet environnement jsdom (vérifié : `window.localStorage` est
// `undefined`, alors que `window.location` est bien là). Tout ce qui garde une préférence côté
// navigateur en dépend — le thème (`pbm-theme`), le guide de première partie (`pbm.jeu.guide-vu`)
// et les réglages de confort (`pbm.jeu.confort`, lot `j-accessibilite-jeu`). Sans ce double, ces
// crochets ne sont testables qu'à travers leur `try/catch`, c'est-à-dire pas du tout : on
// vérifierait seulement qu'ils survivent à l'absence de stockage, jamais qu'ils stockent.
if (!window.localStorage) {
  const memoire = new Map<string, string>();
  const faux: Storage = {
    get length() {
      return memoire.size;
    },
    clear: () => memoire.clear(),
    getItem: (cle) => memoire.get(cle) ?? null,
    key: (index) => Array.from(memoire.keys())[index] ?? null,
    removeItem: (cle) => void memoire.delete(cle),
    setItem: (cle, valeur) => void memoire.set(cle, String(valeur)),
  };
  Object.defineProperty(window, "localStorage", { value: faux, configurable: true });
}

// jsdom n'implémente pas les URL d'objet (aperçus de photos, lot v3-upload).
if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:mock";
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => {};
}

// jsdom n'implémente pas `ResizeObserver` : Recharts' `ResponsiveContainer` (courbes de valeur,
// lots `v4-dashboard`/`v4-fiche`) en a besoin pour mesurer son conteneur, sinon `ReferenceError`
// au montage de tout test qui rend l'un ou l'autre.
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
