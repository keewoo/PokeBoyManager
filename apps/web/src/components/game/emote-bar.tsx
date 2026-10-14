"use client";

import { useCallback, useEffect, useState } from "react";

import { getReglagesEmotes, setReglagesEmotes } from "@/lib/api/emotes";
import {
  DUREE_BULLE_MS,
  EMOTES,
  type CodeEmote,
  type EmoteRecue,
  emoteDuCode,
} from "@/lib/game/emotes";
import { cn } from "@/lib/utils";

/**
 * La **palette d'emotes** d'une partie (lot `j-echanges-emotes`, décision DJ10).
 *
 * Dix phrases prédéfinies, un interrupteur pour les couper, et **aucun champ de saisie**. Ce n'est
 * pas une limitation technique : un chat libre entre un adulte et un enfant de onze ans demanderait
 * une modération que ce projet n'aura pas, alors qu'une liste fermée de phrases bienveillantes donne
 * la chaleur sans la charge. Le risque nommé du lot est qu'on ajoute « juste un petit chat » plus
 * tard ; un test statique (`apps/api/tests/test_jeu_emotes_parite.py`) interdit l'apparition d'un
 * champ de texte dans l'interface de plateau, pour que cette décision ne se perde pas.
 *
 * **Couper les emotes est immédiat et mémorisé**, et les deux mots comptent :
 *
 * - *immédiat* — l'écran se replie sur-le-champ (palette masquée, bulles ignorées) **et** le serveur
 *   relit le réglage à chaque emote : la prochaine emote de l'adversaire ne part déjà plus. Rien à
 *   rouvrir, rien à rafraîchir ;
 * - *mémorisé* — le réglage est écrit côté compte (`PATCH /jeu/emotes/reglages`), pas dans ce
 *   navigateur : il vaut aussi pour la partie suivante, et sur un autre appareil.
 *
 * L'interrupteur est **un seul pour les deux sens** (je ne reçois plus, je n'envoie plus). Un
 * demi-réglage — « je ne te lis pas mais je te parle » — est exactement la position qui sert à
 * narguer ; et un interrupteur unique se comprend d'un coup d'œil.
 *
 * **Hors du flux, sur le flanc droit, et c'est une contrainte.** La page du plateau ne tolère aucun
 * défilement (e2e `plateau-responsive`), donc le composant est `fixed` : il n'allonge jamais la
 * page. Les coins sont déjà pris, et deux portent des boutons que l'e2e clique vraiment :
 *
 * | Emplacement | Qui l'occupe |
 * |---|---|
 * | haut gauche | le tiroir d'aide (`aide-panel.tsx`, borné à 15rem) |
 * | haut centre | le statut de connexion (`game-board.tsx`) |
 * | haut droite | `anim-accelere` / `anim-sauter` (`animation-layer.tsx`) |
 * | bas, centré | le journal de partie (`journal-panel.tsx`) |
 * | bas gauche | l'écran de fin replié (`fin-partie.tsx`) |
 * | **flanc droit, à mi-hauteur** | **ici** — le seul emplacement libre en paysage comme en portrait |
 *
 * L'emote part par le **canal temps réel** et par lui seul. En connexion dégradée (repli en
 * interrogation HTTP), la palette le **dit** au lieu de faire semblant : donner une file d'attente à
 * une emote obligerait à la stocker, et une emote qui arrive dix secondes trop tard ne veut plus
 * rien dire.
 */
export type EmoteBarProps = {
  /**
   * Envoie une emote ; renvoie `false` si le canal direct n'est pas ouvert. C'est `CanalPartie`
   * qui la transmet — ce composant ne connaît ni URL, ni WebSocket.
   */
  onEnvoyer: (code: CodeEmote) => boolean;
  /**
   * La dernière emote reçue, **nouvelle référence à chaque réception** (c'est ce changement
   * d'identité qui rallume la bulle, même pour deux emotes identiques de suite).
   */
  recue?: (EmoteRecue & { cle: number }) | null;
  /** Le dernier refus du serveur (débit, emotes coupées) : affiché tel qu'il l'a rédigé. */
  refus?: { code: string; message: string } | null;
  /** Vrai quand le canal est en direct : hors direct, les emotes ne circulent pas. */
  direct: boolean;
};

export function EmoteBar({ onEnvoyer, recue, refus, direct }: EmoteBarProps) {
  const [ouvert, setOuvert] = useState(false);
  // `null` = réglage pas encore connu : on n'affiche rien plutôt que de supposer « coupé » (ce
  // serait masquer une fonctionnalité) ou « ouvert » (ce serait montrer une palette qu'on va
  // refermer sous les doigts du joueur).
  const [recevoir, setRecevoir] = useState<boolean | null>(null);
  const [bulle, setBulle] = useState<(EmoteRecue & { cle: number }) | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    getReglagesEmotes()
      .then((r) => {
        if (actif) setRecevoir(r.recevoir_emotes);
      })
      .catch(() => {
        // Une panne de lecture n'est pas un refus : on suit le défaut DJ10 (« j'échange ») plutôt
        // que de priver le joueur d'une fonctionnalité à cause d'un réseau qui a hoqueté. Le
        // serveur reste autorité — il refusera l'envoi si le réglage dit le contraire, et la
        // palette affichera sa raison.
        if (actif) setRecevoir(true);
      });
    return () => {
      actif = false;
    };
  }, []);

  // Une emote reçue s'affiche quelques secondes puis disparaît. Rien n'est conservé : il n'y a ni
  // historique, ni compteur — c'est la même promesse que côté serveur.
  useEffect(() => {
    // `recevoir !== true` couvre les deux cas où rien ne doit s'afficher, **et efface ce qui le
    // serait déjà** : le joueur vient de couper (une emote peut être en vol), ou le réglage n'est
    // pas encore connu. Sans cette remise à zéro, une emote arrivée pendant le chargement du
    // réglage resterait à l'écran d'un joueur qui a précisément demandé le silence.
    if (recevoir !== true) {
      setBulle(null);
      return;
    }
    if (!recue) return;
    if (!emoteDuCode(recue.code)) return; // code inconnu de cet écran : on ne devine pas
    setBulle(recue);
    const minuteur = setTimeout(() => setBulle(null), DUREE_BULLE_MS);
    return () => clearTimeout(minuteur);
  }, [recue, recevoir]);

  // Le refus du serveur s'affiche avec sa phrase (jamais un refus muet), et s'effface de lui-même.
  useEffect(() => {
    if (!refus) return;
    setMessage(refus.message);
    const minuteur = setTimeout(() => setMessage(null), DUREE_BULLE_MS);
    return () => clearTimeout(minuteur);
  }, [refus]);

  const basculer = useCallback(async () => {
    const vise = !(recevoir ?? true);
    // Optimiste : l'interrupteur doit répondre tout de suite (« immédiat »). On revient en arrière
    // si le serveur refuse — et on le dit, plutôt que de laisser un réglage mentir.
    setRecevoir(vise);
    if (!vise) setBulle(null);
    try {
      const r = await setReglagesEmotes({ recevoir_emotes: vise });
      setRecevoir(r.recevoir_emotes);
    } catch {
      setRecevoir(!vise);
      setMessage("Réglage non enregistré. Réessaie dans un instant.");
    }
  }, [recevoir]);

  const envoyer = useCallback(
    (code: CodeEmote) => {
      setOuvert(false);
      if (!onEnvoyer(code)) {
        setMessage("Les emotes demandent la connexion directe.");
      }
    },
    [onEnvoyer],
  );

  if (recevoir === null) return null;

  const emoteBulle = bulle ? emoteDuCode(bulle.code) : null;

  return (
    // Hors flux (`fixed`) : la palette n'allonge jamais la page du plateau. `pointer-events-none`
    // sur l'enveloppe laisse le plateau cliquable autour ; seuls les panneaux captent les clics.
    <div
      data-testid="emotes"
      className="pointer-events-none fixed right-2 top-1/2 z-30 flex -translate-y-1/2 items-center gap-2"
    >
      {/* La bulle de l'emote reçue, à gauche de la palette — jamais au centre du plateau. */}
      {emoteBulle && (
        <div
          data-testid="emote-bulle"
          data-de={bulle?.de}
          role="status"
          className={cn(
            "pointer-events-none max-w-[12rem] rounded-2xl border px-3 py-1.5 text-sm font-semibold shadow-lg",
            bulle?.de === "moi"
              ? "border-[rgba(157,0,255,0.45)] bg-[rgba(20,27,92,0.95)] text-foreground"
              : "border-gold/60 bg-[rgba(242,193,78,0.16)] text-gold",
          )}
        >
          <span aria-hidden className="mr-1">
            {emoteBulle.pictogramme}
          </span>
          {emoteBulle.phrase}
        </div>
      )}

      {message && (
        <div
          data-testid="emotes-message"
          role="status"
          className="pointer-events-none max-w-[12rem] rounded-lg border border-[rgba(226,59,59,0.5)] bg-[rgba(226,59,59,0.16)] px-2 py-1 text-xs text-[#F2A197]"
        >
          {message}
        </div>
      )}

      <section
        aria-label="Emotes"
        className="pointer-events-auto flex flex-col items-end gap-1 rounded-2xl border border-[rgba(157,0,255,0.35)] bg-[linear-gradient(160deg,#141B5C,#0A1048)] p-1 shadow-[0_8px_30px_-12px_rgba(0,0,0,0.8)]"
      >
        {/* Ouvrir la palette. Masquée quand le joueur a coupé les emotes : on ne propose pas un
            geste que le serveur refusera. */}
        {recevoir && (
          <button
            type="button"
            data-testid="emotes-ouvrir"
            aria-expanded={ouvert}
            aria-controls="emotes-palette"
            aria-label={ouvert ? "Fermer les emotes" : "Envoyer une emote"}
            disabled={!direct}
            title={direct ? undefined : "Les emotes demandent la connexion directe."}
            onClick={() => setOuvert((o) => !o)}
            className="rounded-xl px-2 py-1 text-lg leading-none disabled:opacity-40"
          >
            <span aria-hidden>💬</span>
          </button>
        )}

        {recevoir && ouvert && (
          <ul
            id="emotes-palette"
            data-testid="emotes-palette"
            className="flex max-h-[14rem] w-[12.5rem] flex-col gap-0.5 overflow-y-auto"
          >
            {EMOTES.map((emote) => (
              <li key={emote.code}>
                <button
                  type="button"
                  data-testid={`emote-${emote.code}`}
                  onClick={() => envoyer(emote.code)}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-sm hover:bg-[rgba(255,255,255,0.08)]"
                >
                  <span aria-hidden>{emote.pictogramme}</span>
                  <span className="min-w-0 flex-1 truncate">{emote.phrase}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* L'interrupteur, toujours visible : couper doit être à un clic, et rétablir aussi. Un
            bouton `switch` plutôt qu'une case à cocher — aucun élément de saisie dans le plateau. */}
        <button
          type="button"
          role="switch"
          aria-checked={recevoir}
          data-testid="emotes-interrupteur"
          aria-label={recevoir ? "Couper les emotes" : "Rétablir les emotes"}
          onClick={() => void basculer()}
          className={cn(
            "rounded-xl px-2 py-0.5 text-[0.65rem] font-semibold",
            recevoir ? "text-muted-foreground hover:text-gold" : "text-gold",
          )}
        >
          {recevoir ? "couper" : "emotes coupées"}
        </button>
      </section>
    </div>
  );
}
