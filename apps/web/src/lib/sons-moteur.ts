/**
 * Le **moteur de synthèse** (lot `j-son`) : ce qui transforme une {@link Recette} en son réel.
 *
 * C'est le seul fichier du lot qui touche le navigateur. Tout ce qui décide — quel son pour quel
 * événement, à quel volume relatif, dans quel ordre — vit dans `lib/game/sons.ts`, pur et testé
 * sans navigateur. Ici il ne reste que du câblage Web Audio.
 *
 * ## Pourquoi un `AudioContext` ne se crée pas au chargement
 *
 * Les navigateurs refusent de jouer un son avant une interaction de l'utilisateur, et c'est le
 * troisième critère d'acceptation du lot. Mais la règle est plus subtile qu'un refus : un
 * `AudioContext` créé trop tôt naît **suspendu**, et Chrome écrit un avertissement dans la console
 * de chaque visiteur. La parade n'est donc pas de le créer et de le reprendre — c'est de ne pas le
 * créer du tout : {@link creerMoteur} n'est appelé qu'au premier geste réel du joueur
 * (`lib/sons-provider.tsx`). Avant, il n'existe aucun objet audio, donc rien ne peut sonner.
 *
 * ## Le mode silencieux du système est respecté en ne le contournant PAS
 *
 * Il n'existe aucune interface web qui dise « ce téléphone est en silencieux ». Ce que le lot
 * demande — « des sons qui respectent le mode silencieux du système » — s'obtient en laissant le
 * navigateur faire : sur iOS, Web Audio suit l'interrupteur matériel, et le volume système
 * s'applique partout. Le contournement classique (un élément `<audio>` muet joué en boucle pour
 * basculer la page sur le canal « lecture de média ») est **délibérément absent**, et un test de
 * garde vérifie qu'il n'apparaît pas : forcer un son sur un appareil mis en silencieux, c'est
 * passer outre une demande explicite de son propriétaire.
 */

import { type Forme, type Recette, bornerGain } from "@/lib/game/sons";

/** Les deux objets qu'on garde ouverts pour toute la session audio. */
export type Moteur = {
  /** Le contexte, créé au premier geste du joueur et jamais avant. */
  ctx: AudioContext;
  /** Le volume général : un seul nœud à toucher pour couper, et la coupure est alors immédiate. */
  maitre: GainNode;
  /** Le bruit blanc, fabriqué une fois et réutilisé (en refaire un par son coûterait pour rien). */
  bruit: AudioBuffer;
};

/** Durée du tampon de bruit blanc, en secondes : plus long que le plus long des sons. */
const DUREE_BRUIT = 2;

/** Correspondance entre nos formes d'onde et le vocabulaire de Web Audio. */
const FORMES: Record<Exclude<Forme, "bruit">, OscillatorType> = {
  sinus: "sine",
  triangle: "triangle",
  carre: "square",
  scie: "sawtooth",
};

/**
 * Fabrique le tampon de bruit blanc — le « souffle » des recettes qui en contiennent.
 *
 * Du bruit, et non un échantillon enregistré : c'est ce qui permet au crépitement du Feu et au
 * froissement d'une carte piochée de n'avoir aucune origine externe (donc aucune licence).
 */
export function creerBruit(ctx: BaseAudioContext): AudioBuffer {
  const n = Math.floor(ctx.sampleRate * DUREE_BRUIT);
  const tampon = ctx.createBuffer(1, n, ctx.sampleRate);
  const donnees = tampon.getChannelData(0);
  for (let i = 0; i < n; i += 1) donnees[i] = Math.random() * 2 - 1;
  return tampon;
}

/**
 * Ouvre le moteur audio. **À n'appeler qu'au premier geste du joueur.**
 *
 * @param fabrique comment obtenir un `AudioContext` — injecté pour qu'un test puisse en passer un
 *                 faux, et pour que ce module ne lise jamais `window` lui-même.
 * @param volume   volume général initial, dans `[0, 1]`.
 */
export function creerMoteur(fabrique: () => AudioContext, volume: number): Moteur {
  const ctx = fabrique();
  const maitre = ctx.createGain();
  maitre.gain.value = Math.min(1, Math.max(0, volume));
  maitre.connect(ctx.destination);
  return { ctx, maitre, bruit: creerBruit(ctx) };
}

/** Change le volume général. Immédiat : c'est par là que passe la coupure. */
export function reglerVolume(moteur: Moteur, volume: number): void {
  moteur.maitre.gain.value = Math.min(1, Math.max(0, volume));
}

/**
 * Joue une recette **maintenant**, et programme son extinction.
 *
 * L'enveloppe est posée en rampes sur le gain de chaque composante, jamais en valeur brute : une
 * onde qui démarre à plein volume produit un claquement audible (le « clic » de l'audio
 * numérique), qui est exactement ce qui fait qu'un son synthétisé paraît bon marché.
 *
 * Tous les nœuds créés ici sont **jetables** : ils s'arrêtent d'eux-mêmes (`stop`) et le navigateur
 * les libère. Rien n'est à nettoyer, donc rien ne fuit si le joueur quitte la page au milieu d'un
 * K.O.
 *
 * @param gainRelatif facteur supplémentaire dans `[0, 1]` — utilisé par la musique d'ambiance pour
 *                    passer sous le plafond des bruitages sans toucher au volume général.
 */
export function jouerRecette(moteur: Moteur, recette: Recette, gainRelatif = 1): void {
  const { ctx, maitre, bruit } = moteur;
  const t0 = ctx.currentTime;
  const duree = recette.duree / 1000;

  // Un passe-bas commun à toute la recette : c'est lui qui enlève l'agressivité des harmoniques
  // aiguës d'une carrée ou d'une scie, sans qu'on ait à renoncer à ces formes.
  const filtre = ctx.createBiquadFilter();
  filtre.type = "lowpass";
  filtre.frequency.value = recette.passeBas;
  filtre.connect(maitre);

  const gainTotal = bornerGain(recette.gain) * Math.min(1, Math.max(0, gainRelatif));

  for (const partiel of recette.partiels) {
    const depart = t0 + partiel.retard / 1000;
    // La composante s'éteint avec le son entier, pas à sa propre durée : décaler le départ sans
    // décaler la fin est exactement ce qui fait les sons à deux temps (la pièce qui retombe).
    const fin = t0 + duree;
    if (fin <= depart) continue;

    const gain = ctx.createGain();
    gain.connect(filtre);

    const niveau = gainTotal * partiel.poids;
    const montee = Math.min(recette.attaque / 1000, (fin - depart) / 2);
    const descente = Math.min(recette.chute / 1000, fin - depart - montee);
    gain.gain.setValueAtTime(0, depart);
    gain.gain.linearRampToValueAtTime(niveau, depart + montee);
    // Tenue jusqu'au début de la descente, puis extinction. `linearRamp` et non
    // `exponentialRamp` : l'exponentielle refuse la valeur zéro et laisse une queue audible.
    gain.gain.setValueAtTime(niveau, Math.max(depart + montee, fin - descente));
    gain.gain.linearRampToValueAtTime(0, fin);

    if (partiel.forme === "bruit") {
      const source = ctx.createBufferSource();
      source.buffer = bruit;
      source.connect(gain);
      source.start(depart);
      source.stop(fin);
      continue;
    }

    const osc = ctx.createOscillator();
    osc.type = FORMES[partiel.forme];
    osc.frequency.setValueAtTime(partiel.depart, depart);
    // Le glissando : c'est lui qui fait qu'un son « monte » (évolution, victoire) ou « tombe »
    // (K.O., défaite). Sans lui, deux sons de même timbre racontent la même chose.
    if (partiel.arrivee !== partiel.depart) {
      osc.frequency.linearRampToValueAtTime(partiel.arrivee, fin);
    }
    osc.connect(gain);
    osc.start(depart);
    osc.stop(fin);
  }
}

/**
 * Joue une note tenue — la brique de la musique d'ambiance.
 *
 * Elle n'emprunte pas {@link jouerRecette} parce qu'elle n'a pas de partiels : une note de fond est
 * une sinusoïde et rien d'autre. Lui fabriquer une recette à un partiel aurait donné le même son
 * pour plus de code.
 */
export function jouerNote(
  moteur: Moteur,
  frequence: number,
  dureeMs: number,
  gain: number,
  passeBas: number,
  retardMs = 0,
): void {
  const { ctx, maitre } = moteur;
  const depart = ctx.currentTime + retardMs / 1000;
  const fin = depart + dureeMs / 1000;

  const filtre = ctx.createBiquadFilter();
  filtre.type = "lowpass";
  filtre.frequency.value = passeBas;
  filtre.connect(maitre);

  const g = ctx.createGain();
  g.connect(filtre);
  // Montée et descente longues : une note de fond ne doit jamais avoir d'attaque perceptible,
  // sinon elle devient un événement — donc une distraction.
  const quart = (fin - depart) / 4;
  g.gain.setValueAtTime(0, depart);
  g.gain.linearRampToValueAtTime(gain, depart + quart);
  g.gain.setValueAtTime(gain, fin - quart);
  g.gain.linearRampToValueAtTime(0, fin);

  const osc = ctx.createOscillator();
  osc.type = "sine";
  osc.frequency.value = frequence;
  osc.connect(g);
  osc.start(depart);
  osc.stop(fin);
}
