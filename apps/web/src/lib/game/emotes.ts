// Emotes prédéfinies d'une partie, côté navigateur (lot `j-echanges-emotes`, décision DJ10).
//
// DJ10 : « Emotes prédéfinies seulement ("bien joué", "oups", "ton tour"), désactivables, jamais de
// texte libre. » Un chat libre entre un adulte et un enfant de onze ans demanderait une modération
// que ce projet n'aura pas ; une liste fermée de phrases bienveillantes donne la chaleur sans la
// charge.
//
// Ce module est **pur** : la liste, et la traduction d'un code en phrase. Aucun appel réseau, aucun
// état. Le serveur fait autorité — il revalide chaque code contre SON catalogue
// (`apps/api/src/pbm_api/games/emotes.py`) et un test de parité garde les deux listes identiques
// (`apps/api/tests/test_jeu_emotes_parite.py`). Ce doublon est assumé : il évite d'attendre le
// réseau pour ouvrir la palette, et il ne peut pas dériver sans faire rougir la CI.
//
// ⛔ **On ne transmet jamais de texte.** `envoyerEmote` (dans `realtime.ts`) n'accepte qu'un
// `CodeEmote` — une union fermée, donc une faute de frappe ne compile pas. Il n'existe, dans toute
// l'interface de jeu, aucun champ où un joueur écrirait un message à l'autre, et un test statique
// l'empêche d'apparaître demain (le risque nommé du lot : « ajouter juste un petit chat »).

/** Une emote : son code (le seul qui circule), sa phrase et son pictogramme. */
export type Emote = {
  code: string;
  phrase: string;
  pictogramme: string;
};

/**
 * Le catalogue **fermé**, dans l'ordre d'affichage de la palette — salutations, félicitations, puis
 * les emotes qui parlent de soi.
 *
 * La règle qui choisit ces dix-là, et qui doit survivre à toute addition :
 *
 * > **Une emote parle de son auteur, ou félicite l'autre. Jamais l'inverse.**
 *
 * C'est ce qui empêche de narguer sans texte libre : « Oups… » dit *je me suis trompé*, pas *tu t'es
 * trompé*, et aucune emote ne commente le coup de l'adversaire autrement que pour le saluer.
 */
export const EMOTES: readonly Emote[] = [
  { code: "bonjour", phrase: "Bonjour !", pictogramme: "👋" },
  { code: "bonne_partie", phrase: "Bonne partie !", pictogramme: "🎉" },
  { code: "bonne_chance", phrase: "Bonne chance !", pictogramme: "🍀" },
  { code: "bien_joue", phrase: "Bien joué !", pictogramme: "👏" },
  { code: "belle_carte", phrase: "Belle carte !", pictogramme: "✨" },
  { code: "merci", phrase: "Merci !", pictogramme: "🙏" },
  { code: "oups", phrase: "Oups…", pictogramme: "😅" },
  { code: "je_reflechis", phrase: "Je réfléchis…", pictogramme: "🤔" },
  { code: "un_instant", phrase: "Un instant, je reviens", pictogramme: "⏳" },
  { code: "ton_tour", phrase: "À toi de jouer", pictogramme: "👉" },
] as const;

/** Les codes du catalogue, en type : une valeur hors liste ne compile pas. */
export type CodeEmote = (typeof EMOTES)[number]["code"];

/** Index code → emote, pour traduire un code reçu sans parcourir la liste. */
const PAR_CODE: Record<string, Emote> = Object.fromEntries(EMOTES.map((e) => [e.code, e]));

/**
 * L'emote d'un code, ou `null` si le code est inconnu de cet écran.
 *
 * `null` plutôt qu'un repli sur une emote par défaut : afficher « Bien joué ! » parce qu'on n'a pas
 * reconnu le code serait faire dire à l'adversaire ce qu'il n'a pas dit. L'appelant choisit de ne
 * rien montrer — un serveur plus récent que le navigateur reste ainsi sans conséquence visible.
 */
export function emoteDuCode(code: unknown): Emote | null {
  return typeof code === "string" ? (PAR_CODE[code] ?? null) : null;
}

/** Une emote reçue sur le canal : son code, et de qui elle vient. */
export type EmoteRecue = {
  code: string;
  /** `"moi"` est l'écho de mon propre envoi (confirmation) ; `"adversaire"`, l'autre joueur. */
  de: "moi" | "adversaire";
};

/** Durée d'affichage d'une bulle d'emote, en millisecondes. */
export const DUREE_BULLE_MS = 4000;

/** Codes d'erreur que le serveur renvoie à l'émetteur d'une emote (miroir de `emotes.py`). */
export const ERREUR_EMOTE_INCONNUE = "emote_inconnue";
export const ERREUR_EMOTE_TROP_RAPIDE = "emote_trop_rapide";
export const ERREUR_EMOTES_COUPEES = "emotes_coupees";

/** Vrai si ce code d'erreur serveur concerne une emote (et doit donc remonter à la palette). */
export function estErreurEmote(code: unknown): boolean {
  return (
    code === ERREUR_EMOTE_INCONNUE ||
    code === ERREUR_EMOTE_TROP_RAPIDE ||
    code === ERREUR_EMOTES_COUPEES
  );
}
