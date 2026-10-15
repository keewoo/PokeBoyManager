import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Garde d'**origine** des sons (lot `j-son`) : le dépôt ne contient aucun fichier audio, et le code
 * ne contourne pas le mode silencieux du système.
 *
 * Pourquoi une garde statique plutôt qu'une ligne de documentation : le risque nommé par le lot est
 * un risque de **droits**, et il ne se manifeste jamais au moment où on le prend. Quelqu'un —
 * humain ou agent — qui trouvera un `pose.mp3` « parfait » sur un site de bruitages l'ajoutera en
 * trois secondes, la CI restera verte, et la question de la licence ne se posera que le jour où
 * elle coûtera quelque chose. Ce test est le moment où elle se pose.
 *
 * Le premier critère d'acceptation du lot — *« tous les sons sont libres de droits, et leur origine
 * est écrite dans le dépôt »* — est donc tenu de la seule façon qui se vérifie : il n'y a **rien à
 * sourcer**. Chaque son est une recette de `src/lib/game/sons.ts`, fabriquée par le navigateur.
 *
 * ⚠️ Si un jour un fichier audio devient légitime (une voix enregistrée, une musique commandée), ce
 * test doit être **modifié en connaissance de cause**, avec sa licence écrite à côté du fichier —
 * pas supprimé pour faire passer la CI.
 */

// `process.cwd()` vaut `apps/web` — vitest y est lancé par `pnpm --filter @pbm/web test`.
const RACINE_WEB = process.cwd();

/** Les extensions qu'on refuse : tout ce qu'un navigateur sait décoder comme du son. */
const EXTENSIONS_AUDIO = [".mp3", ".ogg", ".wav", ".m4a", ".aac", ".flac", ".opus", ".weba", ".mid"];

/**
 * Retire les commentaires d'un source TypeScript.
 *
 * Indispensable, et pas une commodité : ces gardes portent sur ce que le **code** fait. Les
 * fichiers du lot *expliquent* en commentaire pourquoi le contournement du mode silencieux (un
 * élément `<audio>` muet) est absent — une garde qui lit la prose interdirait donc d'expliquer ce
 * qu'elle interdit, et le premier réflexe serait d'effacer l'explication pour faire passer la CI.
 */
function sansCommentaires(code: string): string {
  return code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

/** Parcourt un dossier et rend tous les chemins de fichiers, récursivement. */
function fichiers(racine: string): string[] {
  const trouves: string[] = [];
  const pile = [racine];
  while (pile.length > 0) {
    const courant = pile.pop();
    if (!courant) continue;
    for (const entree of readdirSync(courant)) {
      const complet = path.join(courant, entree);
      if (statSync(complet).isDirectory()) pile.push(complet);
      else trouves.push(complet);
    }
  }
  return trouves;
}

describe("origine des sons — il n'y a rien à créditer", () => {
  it("ne contient AUCUN fichier audio dans les ressources publiques", () => {
    const publics = fichiers(path.resolve(RACINE_WEB, "public"));
    const audio = publics.filter((f) => EXTENSIONS_AUDIO.includes(path.extname(f).toLowerCase()));
    expect(
      audio.map((f) => path.relative(RACINE_WEB, f)),
      "un fichier audio est apparu : sa licence doit être écrite à côté de lui, ou il doit partir",
    ).toEqual([]);
  });

  it("ne charge aucun son depuis une URL : ni `fetch`, ni `Audio`, ni `decodeAudioData`", () => {
    // Les trois seules façons de faire entrer un son venu d'ailleurs dans une page. Les interdire
    // dans la couche sonore ferme la porte que le test précédent verrouille côté dépôt : un son
    // peut très bien venir d'un CDN sans qu'aucun fichier n'entre dans le dépôt.
    const sources = [
      "src/lib/game/sons.ts",
      "src/lib/sons-moteur.ts",
      "src/lib/sons-provider.tsx",
      "src/components/game/son-layer.tsx",
    ];
    for (const relatif of sources) {
      const code = sansCommentaires(readFileSync(path.resolve(RACINE_WEB, relatif), "utf-8"));
      expect(code, `${relatif} : un son chargé depuis une URL`).not.toMatch(/decodeAudioData/);
      expect(code, `${relatif} : un élément <audio> ou new Audio()`).not.toMatch(/new Audio\(/);
      expect(code, `${relatif} : une URL de média`).not.toMatch(/https?:\/\/[^\s"']+\.(mp3|ogg|wav|m4a)/i);
    }
  });

  it("ne contourne PAS le mode silencieux du système", () => {
    // Le contournement connu est un élément `<audio playsinline>` muet joué en boucle, qui fait
    // basculer la page sur le canal « lecture de média » d'iOS — où l'interrupteur matériel de
    // silence ne s'applique plus. Il n'a aucune autre utilité que celle-là. L'exigence du lot
    // (« des sons respectant le mode silencieux du système ») se tient en ne le posant pas : on
    // laisse le navigateur appliquer le réglage de l'appareil, et on ne le défait pas.
    const sources = ["src/lib/sons-moteur.ts", "src/lib/sons-provider.tsx", "src/components/game/son-layer.tsx"];
    for (const relatif of sources) {
      const code = sansCommentaires(readFileSync(path.resolve(RACINE_WEB, relatif), "utf-8"));
      expect(code, `${relatif} : <audio> caché`).not.toMatch(/<audio/i);
      expect(code, `${relatif} : astuce playsinline`).not.toMatch(/playsinline/i);
      expect(code, `${relatif} : catégorie de session audio forcée`).not.toMatch(/setAudioSessionType|audioSession/i);
    }
  });

  it("n'ouvre le contexte audio QUE depuis un geste du joueur", () => {
    // Troisième critère d'acceptation du lot. La propriété est vérifiée au comportement dans
    // `sons-provider.test.tsx` ; ici on garde sa **cause** : un seul endroit du code a le droit
    // d'appeler `creerMoteur`, et c'est l'éveil déclenché par un écouteur de geste.
    const brut = readFileSync(path.resolve(RACINE_WEB, "src/lib/sons-provider.tsx"), "utf-8");
    const provider = sansCommentaires(brut);
    const appels = provider.match(/creerMoteur\(/g) ?? [];
    // Un seul appel (celui d'`eveiller`) — plus l'import nommé, qui ne porte pas de parenthèse.
    expect(appels.length, "creerMoteur ne doit être appelé qu'à un seul endroit").toBe(1);
    // Et `eveiller` doit être branché sur les trois gestes : souris, clavier, tactile. En oublier
    // un laisserait un appareil entier muet sans que rien ne le dise.
    for (const geste of ["pointerdown", "keydown", "touchstart"]) {
      expect(provider, `le geste ${geste} n'ouvre pas le son`).toContain(geste);
    }
  });
});
