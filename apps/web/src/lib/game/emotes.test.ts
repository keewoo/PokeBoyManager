import { describe, expect, it } from "vitest";

import {
  DUREE_BULLE_MS,
  EMOTES,
  ERREUR_EMOTE_TROP_RAPIDE,
  emoteDuCode,
  estErreurEmote,
} from "@/lib/game/emotes";

/**
 * Emotes prédéfinies, côté navigateur (lot `j-echanges-emotes`, DJ10).
 *
 * Deux choses à prouver ici, et la seconde est la vraie :
 *
 * 1. le **catalogue** est fermé et traduit sans deviner ;
 * 2. les codes d'erreur d'emote se reconnaissent, pour qu'un refus remonte à la palette.
 *
 * Le transport (le canal ne doit ni confondre une emote avec un coup, ni l'avaler) est exercé dans
 * `src/__tests__/game-realtime.test.ts`, là où vit déjà le faux WebSocket de `CanalPartie`.
 *
 * La parité avec le catalogue du serveur est gardée côté Python
 * (`apps/api/tests/test_jeu_emotes_parite.py`, qui lit ce fichier-ci) : les deux langages ne
 * partagent aucune constante, donc la parité se vérifie au point de vérité.
 */

describe("catalogue d'emotes", () => {
  it("est fermé : dix emotes, et cette liste exacte", () => {
    // Garde de lecture (même esprit que `test_huit_raisons_de_fin_cote_moteur` côté moteur) : ce
    // test n'interdit pas d'ajouter une emote, il oblige à passer ici — et donc par la règle qui
    // les choisit : une emote parle de son auteur, ou félicite l'autre. Jamais l'inverse.
    expect(EMOTES.map((e) => e.code)).toEqual([
      "bonjour",
      "bonne_partie",
      "bonne_chance",
      "bien_joue",
      "belle_carte",
      "merci",
      "oups",
      "je_reflechis",
      "un_instant",
      "ton_tour",
    ]);
  });

  it("traduit un code connu, et rend null sur un code inconnu plutôt que de deviner", () => {
    expect(emoteDuCode("bien_joue")?.phrase).toBe("Bien joué !");
    // Un serveur plus récent que ce navigateur : on ne replie pas sur une autre emote — ce serait
    // faire dire à l'adversaire ce qu'il n'a pas dit.
    expect(emoteDuCode("emote_du_futur")).toBeNull();
    expect(emoteDuCode(42)).toBeNull();
    expect(emoteDuCode(undefined)).toBeNull();
  });

  it("reconnaît les codes d'erreur d'emote, et eux seuls", () => {
    expect(estErreurEmote(ERREUR_EMOTE_TROP_RAPIDE)).toBe(true);
    expect(estErreurEmote("depuis_invalide")).toBe(false);
  });

  it("affiche une bulle quelques secondes, pas plus", () => {
    // Rien n'est conservé : la durée est bornée côté écran comme le stockage l'est côté serveur.
    expect(DUREE_BULLE_MS).toBeGreaterThan(1000);
    expect(DUREE_BULLE_MS).toBeLessThanOrEqual(10000);
  });
});
