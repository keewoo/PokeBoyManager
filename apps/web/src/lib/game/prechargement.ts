/**
 * Pré-chargement des images d'une partie (lot `j-assets-pipeline`) — la logique, **pure**.
 *
 * Le problème que ça règle : une partie affiche jusqu'à 120 cartes, et le navigateur ne demande une
 * image qu'au moment où il la peint (`loading="lazy"` sur chaque carte du plateau). Un joueur qui
 * pose son premier Pokémon voit donc les cartes apparaître une par une, pendant que la mise en
 * place avance. Sur un téléphone en 4G, c'est la première impression du jeu.
 *
 * On charge donc les images **pendant la mise en place**, dans l'ordre où le joueur en aura besoin,
 * et on lui montre une progression **honnête** — comptée sur les images réellement arrivées, pas
 * sur une minuterie. Un échec compte comme terminé : une image manquante ne doit pas laisser la
 * barre à 93 % pour toujours (l'écran, lui, retombe sur `url_repli`).
 *
 * Ce module ne touche ni au DOM ni au réseau : il dit **quoi** charger et **dans quel ordre**, et
 * tient le compte. Le chargement lui-même est injecté — c'est ce qui le rend testable sans
 * navigateur, et c'est la même séparation que `lib/game/animations.ts` (réducteur pur d'un côté,
 * `requestAnimationFrame` de l'autre).
 *
 * Le budget que ce pré-chargement doit tenir est déclaré côté serveur
 * (`pbm_api.jeu.budget.PLAFOND_MISE_EN_PLACE_OCTETS`, 512 Kio ≈ 2,6 s en 4G) et contrôlé en CI.
 */

import {
  separerCamps,
  type VueCarte,
  type VueJoueur,
  type VuePartie,
  type VuePokemon,
} from "@/lib/game/plateau";

/** L'état d'un pré-chargement en cours, tel que la barre de progression le lit. */
export type EtatPrechargement = {
  /** Nombre d'images à charger — figé au démarrage, sinon la barre reculerait. */
  total: number;
  /** Images arrivées (décodées par le navigateur). */
  chargees: number;
  /** Images qui n'arriveront pas. Comptées comme traitées : la barre doit pouvoir finir. */
  echouees: number;
  /** `true` quand il n'y a plus rien à attendre — y compris s'il n'y avait rien à charger. */
  termine: boolean;
};

/** L'état de départ : rien à attendre tant qu'on n'a pas vu la vue de la partie. */
export const ETAT_INITIAL: EtatPrechargement = {
  total: 0,
  chargees: 0,
  echouees: 0,
  termine: true,
};

/**
 * L'avancée **cumulée sur toute la partie**, celle que lit la barre de progression.
 *
 * Distincte de {@link EtatPrechargement}, qui ne décrit qu'**un lot**. La vue d'une partie change à
 * chaque coup et à chaque resynchronisation : de nouvelles cartes deviennent visibles, donc de
 * nouveaux lots démarrent. Afficher l'état du dernier lot ferait reculer la barre — et, pire, la
 * laisserait figée si un lot en cours était abandonné au profit d'un lot vide (c'est le défaut que
 * l'e2e en 4G a trouvé).
 */
export type AvanceeGlobale = {
  /** Total d'images demandées depuis le début de la partie. */
  total: number;
  /** Images arrivées ou définitivement manquées — dans les deux cas, plus rien à attendre d'elles. */
  faits: number;
};

/** Aucune image demandée : la barre n'a rien à dire. */
export const AVANCEE_INITIALE: AvanceeGlobale = { total: 0, faits: 0 };

/**
 * Nombre d'images chargées **en parallèle**.
 *
 * Six : c'est la limite de connexions simultanées par origine des navigateurs en HTTP/1.1, et au
 * delà on ne gagne rien tout en risquant de retarder la requête d'état de la partie — qui, elle,
 * est sur le chemin critique. En HTTP/2 la contrainte n'existe plus, mais l'ordre, lui, compte
 * toujours : six images à la fois garde la file assez courte pour que les premières arrivent vite.
 */
export const PARALLELISME = 6;

/**
 * Les URL d'images à pré-charger, **dans l'ordre d'utilité**, sans doublon.
 *
 * L'ordre n'est pas cosmétique : ce sont les premières images qui décident de ce que le joueur voit
 * pendant qu'il joue son premier tour. Du plus urgent au moins urgent :
 *
 * 1. mes Pokémon en jeu (actif puis banc) et ceux d'en face — ce qui est déjà sur le plateau ;
 * 2. ma main — ce que je vais poser dans les secondes qui suivent ;
 * 3. le reste des cartes visibles (Stade, défausses, zone perdue) — consultable, pas immédiat.
 *
 * On ne prend que `rendu.url` (la variante **plateau**, 12 Ko) : jamais `url_zoom` (45 Ko), qui ne
 * concerne qu'une carte à la fois et à la demande. Charger les deux triplerait le poids d'une
 * partie pour des pixels que personne ne regarde — c'est précisément ce que le budget borne.
 *
 * Les cartes face cachée (pioche, récompenses, main adverse) n'ont pas d'URL du tout : leur dos est
 * **dessiné** par l'écran. Elles ne coûtent donc rien, et n'apparaissent pas ici.
 */
export function urlsAPrecharger(vue: VuePartie | null | undefined): string[] {
  if (!vue) return [];
  // `separerCamps` lève si la vue n'a pas exactement deux joueurs ou si le destinataire n'y est
  // pas : un pré-chargement est un confort, il n'a pas le droit de casser l'écran de partie.
  let moi: VueJoueur;
  let adversaire: VueJoueur;
  try {
    ({ moi, adversaire } = separerCamps(vue));
  } catch {
    return [];
  }

  const urls: string[] = [];
  const vues = new Set<string>();

  const ajouter = (carte: { rendu?: { url: string } } | null | undefined) => {
    const url = carte?.rendu?.url;
    if (!url || vues.has(url)) return;
    vues.add(url);
    urls.push(url);
  };
  const ajouterPokemon = (pokemon: VuePokemon | null | undefined) => {
    if (!pokemon) return;
    // Toute la pile d'évolutions, pas seulement la carte du dessus : le joueur peut la consulter
    // sans quitter le plateau, et l'ordre importe peu puisqu'on dédoublonne.
    pokemon.cartes?.forEach((carte: VueCarte) => ajouter(carte));
    pokemon.energies?.forEach((carte: VueCarte) => ajouter(carte));
    ajouter(pokemon.outil);
  };

  for (const camp of [moi, adversaire]) {
    ajouterPokemon(camp.actif);
    camp.banc?.forEach(ajouterPokemon);
  }
  moi.main?.forEach(ajouter);
  ajouter(vue.stade);
  vue.demande?.options_cartes?.forEach(ajouter);
  for (const camp of [moi, adversaire]) {
    camp.defausse?.forEach(ajouter);
    camp.zone_perdue?.forEach(ajouter);
  }

  return urls;
}

/** Charge une URL et rend une promesse qui **ne rejette jamais** : `true` = arrivée, `false` = non. */
export type ChargeurImage = (url: string) => Promise<boolean>;

/**
 * Le chargeur réel : une `Image` hors document, qui remplit le cache HTTP du navigateur.
 *
 * `new Image()` plutôt qu'un `<link rel="preload">` : on a besoin de **savoir** quand chaque image
 * est arrivée pour que la progression soit honnête, et un `link` ne le dit pas de façon fiable
 * selon les navigateurs. `decode()` attend en plus que l'image soit *décodée*, donc prête à peindre
 * sans saccade — mais son absence (navigateurs anciens) n'est pas une erreur : on retombe sur
 * `onload`, qui garantit déjà le cache rempli.
 */
export function chargeurNavigateur(url: string): Promise<boolean> {
  return new Promise<boolean>((resoudre) => {
    const image = new Image();
    image.onload = () => {
      const decodee = image.decode?.();
      if (decodee) {
        decodee.then(
          () => resoudre(true),
          () => resoudre(true),
        );
        return;
      }
      resoudre(true);
    };
    image.onerror = () => resoudre(false);
    image.src = url;
  });
}

/**
 * Pré-charge `urls` avec au plus {@link PARALLELISME} requêtes de front, en signalant l'avancée.
 *
 * `surAvancee` est appelée après **chaque** image (arrivée ou non) : c'est ce qui rend la barre
 * honnête. La promesse rendue ne rejette jamais — un pré-chargement est un confort, il n'a pas le
 * droit de casser l'écran de partie.
 *
 * `interrompu` permet à l'écran d'abandonner (le joueur a quitté la page) sans attendre les images
 * restantes : sans ça, un démontage de composant laisserait des requêtes en vol et des appels
 * d'avancée sur un état mort.
 */
export async function precharger(
  urls: string[],
  surAvancee: (etat: EtatPrechargement) => void,
  options: { charger?: ChargeurImage; interrompu?: () => boolean } = {},
): Promise<EtatPrechargement> {
  const charger = options.charger ?? chargeurNavigateur;
  const interrompu = options.interrompu ?? (() => false);
  const total = urls.length;
  let chargees = 0;
  let echouees = 0;
  let suivante = 0;

  const etat = (): EtatPrechargement => ({
    total,
    chargees,
    echouees,
    termine: chargees + echouees >= total,
  });

  if (total === 0) {
    const vide = etat();
    surAvancee(vide);
    return vide;
  }
  surAvancee({ total, chargees: 0, echouees: 0, termine: false });

  // Un « ouvrier » prend l'URL suivante dès qu'il a fini la sienne, plutôt que de découper la liste
  // en tranches fixes : une image lente ne retient alors pas les suivantes de sa tranche.
  const ouvrier = async () => {
    while (!interrompu()) {
      const url = urls[suivante++];
      if (url === undefined) return;
      const ok = await charger(url);
      if (ok) chargees += 1;
      else echouees += 1;
      if (!interrompu()) surAvancee(etat());
    }
  };

  await Promise.all(
    Array.from({ length: Math.min(PARALLELISME, total) }, () => ouvrier()),
  );
  return etat();
}

/**
 * La progression en pourcentage entier, 0 à 100.
 *
 * 100 quand il n'y a rien à charger : une barre vide qui annonce 0 % ferait croire à une attente
 * qui n'existe pas.
 */
export function pourcentage(etat: EtatPrechargement): number {
  return pourcentageDe(etat.chargees + etat.echouees, etat.total);
}

/**
 * La part de ``faits`` sur ``total``, en pourcentage entier — la primitive des deux compteurs.
 *
 * 100 quand il n'y a rien à charger : une barre vide qui annonce 0 % ferait croire à une attente
 * qui n'existe pas.
 */
export function pourcentageDe(faits: number, total: number): number {
  if (total <= 0) return 100;
  return Math.max(0, Math.min(100, Math.round((faits / total) * 100)));
}
