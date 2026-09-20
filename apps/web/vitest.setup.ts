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
