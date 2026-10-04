/**
 * Logique **pure** des fenêtres de décision (lot `j-plateau-decisions`).
 *
 * Quand une carte réclame un choix à un joueur, le moteur suspend la résolution et pose une
 * `VueDemande` dans l'état projeté (lot `j-effets-choix`). Ce module porte tout ce qui se raisonne
 * **sans React** autour de cette demande — pour le tester en mémoire, à l'identique du moteur :
 *
 * - `choixParDefaut` : ce qui se joue à l'expiration du délai, **miroir exact** de
 *   `pbm_game.demandes.modele.reponse_par_defaut`, pour l'afficher AVANT l'expiration ;
 * - `reponseValide` : si une sélection est recevable, **miroir** de `valider_reponse`, pour activer
 *   ou griser le bouton « Valider » sans jamais réécrire la règle (le serveur reste l'autorité) ;
 * - `filtrerOptions` / `typesPresents` : la recherche et les filtres qui rendent une pioche de
 *   soixante cartes fouillable en moins de cinq secondes ;
 * - `deplacer` : le réordonnancement d'une demande « ordre ».
 *
 * Aucune de ces fonctions ne décide à la place du serveur : elles anticipent sa réponse pour guider
 * l'écran, et le coup soumis est **rejoué et validé** côté serveur dans tous les cas.
 */

import type { VueDemande, VueOptionCarte } from "@/lib/game/plateau";

/**
 * Le type d'action à soumettre pour répondre à une demande (miroir de
 * `pbm_game.journal.modele.ACTION_REPONDRE_DEMANDE`). La réponse voyage par la **même** route que
 * tout coup (`POST /games/{id}/actions`) : le serveur la rejoue et l'impose au destinataire.
 */
export const ACTION_REPONDRE_DEMANDE = "repondre_demande";

/** Les deux réponses d'une demande oui/non (miroir de `OUI`/`NON` du moteur). */
export const OUI = "oui";
export const NON = "non";

/**
 * Normalise une chaîne pour une recherche **indulgente** : minuscules, sans accents. Un enfant qui
 * tape « dracaufeu » trouve « Dracaufeu », « pokeball » trouve « Poké Ball » — le jeu est celui d'un
 * enfant de onze ans, la recherche ne doit pas lui demander l'orthographe exacte ni les accents.
 *
 * `\p{Diacritic}` (avec le drapeau `u`) retire, après décomposition NFD, les accents combinants
 * séparés de leur lettre : « é » → « e ». Pas de plage combinante en dur dans le source (fragile à
 * l'encodage), une propriété Unicode lisible à la place.
 */
export function normaliser(texte: string): string {
  return texte
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/**
 * Les options filtrées par texte libre (sur le nom **ou** la référence) et par type. `requete` vide
 * = pas de filtre texte ; `type` à `null` = tous les types. **Garde l'ordre d'origine** : il porte
 * du sens pour la catégorie « ordre », et reste stable pour l'œil quand on tape dans la recherche.
 */
export function filtrerOptions(
  options: VueOptionCarte[],
  requete: string,
  type: string | null,
): VueOptionCarte[] {
  const q = normaliser(requete.trim());
  return options.filter((o) => {
    if (type !== null && (o.type ?? null) !== type) return false;
    if (q && !normaliser(o.nom).includes(q) && !normaliser(o.ref).includes(q)) return false;
    return true;
  });
}

/**
 * Les types distincts présents dans les options, dans l'ordre de première apparition — pour dessiner
 * les puces de filtre. Les options sans type connu ne produisent aucune puce (jamais de type inventé).
 */
export function typesPresents(options: VueOptionCarte[]): string[] {
  const vus: string[] = [];
  for (const o of options) {
    const t = o.type ?? null;
    if (t !== null && !vus.includes(t)) vus.push(t);
  }
  return vus;
}

/**
 * Déplace l'élément d'index `de` vers l'index `vers` dans une **copie** de la liste (réordonnancement
 * d'une demande « ordre »). Indices hors bornes ou identiques : la liste est renvoyée inchangée — une
 * interface ne force jamais une transition que l'état n'autorise pas.
 */
export function deplacer<T>(liste: T[], de: number, vers: number): T[] {
  if (de < 0 || de >= liste.length || vers < 0 || vers >= liste.length || de === vers) {
    return liste.slice();
  }
  const copie = liste.slice();
  const [element] = copie.splice(de, 1);
  copie.splice(vers, 0, element as T);
  return copie;
}

/**
 * Les identifiants retenus par la **réponse par défaut** appliquée à l'expiration du délai — miroir
 * exact de `pbm_game.demandes.modele.reponse_par_defaut`. Sert à montrer, AVANT l'expiration, ce qui
 * se passera si le joueur ne répond pas (critère : « réponse par défaut visible »). Déterministe,
 * donc rejouable comme côté serveur.
 *
 * - facultatif → abandon (liste vide) ;
 * - `carte` / `type` / `oui_non` → la **première** option (oui/non sans option explicite → « non ») ;
 * - `cartes` → les `minimum` premières options ;
 * - `ordre` → l'ordre identité (les options telles quelles) ;
 * - `nombre` → la borne `minimum`.
 */
export function choixParDefaut(demande: VueDemande): string[] {
  if (!demande.obligatoire) return [];
  const opts = demande.options ?? [];
  switch (demande.categorie) {
    case "carte":
    case "type":
      return opts.length ? [opts[0] as string] : [];
    case "cartes":
      return opts.slice(0, demande.minimum);
    case "ordre":
      return opts.slice();
    case "oui_non":
      return [opts.length ? (opts[0] as string) : NON];
    case "nombre":
      return [String(demande.minimum)];
    default:
      return [];
  }
}

/**
 * `true` si la sélection `choix` est **recevable** pour la demande — miroir de
 * `pbm_game.demandes.modele.valider_reponse`. Une sélection vide est l'abandon d'un effet facultatif
 * (refusé si la demande est obligatoire). On ne soumet jamais un coup que cette fonction déclare
 * irrecevable, mais c'est bien le serveur qui tranche in fine (il rejoue la réponse).
 */
export function reponseValide(demande: VueDemande, choix: string[]): boolean {
  if (choix.length === 0) return !demande.obligatoire; // abandon : permis si facultatif
  if (new Set(choix).size !== choix.length) return false; // jamais de doublon
  const opts = demande.options ?? [];
  switch (demande.categorie) {
    case "carte":
    case "type":
      return choix.length === 1 && opts.includes(choix[0] as string);
    case "cartes":
      return (
        choix.length >= demande.minimum &&
        choix.length <= demande.maximum &&
        choix.every((c) => opts.includes(c))
      );
    case "ordre": {
      const a = choix.slice().sort();
      const b = opts.slice().sort();
      return a.length === b.length && a.every((v, i) => v === b[i]);
    }
    case "oui_non":
      return choix.length === 1 && (choix[0] === OUI || choix[0] === NON);
    case "nombre": {
      if (choix.length !== 1) return false;
      const n = Number(choix[0]);
      return Number.isInteger(n) && n >= demande.minimum && n <= demande.maximum;
    }
    default:
      return false;
  }
}
