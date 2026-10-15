import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

// Lot `j-assets-pipeline`, critère : « le pré-chargement se termine avant la fin de la mise en
// place dans les conditions de test (4G simulée) ».
//
// Ce que ce test prouve, et qu'aucun test unitaire ne peut prouver : sur un lien 4G, les images
// d'un plateau arrivent **dans le temps que met un joueur à poser ses cartes**. La logique de
// pré-chargement est couverte en unitaire (`src/lib/game/prechargement.test.ts`) ; ici on mesure le
// temps de bout en bout, dans un vrai navigateur.
//
// **Comment la 4G est simulée, et pourquoi pas par CDP.** `Network.emulateNetworkConditions` ne
// s'applique pas aux réponses fabriquées par `route.fulfill` (elles ne traversent pas la pile
// réseau) : un bridage CDP donnerait ici un test qui ne mesure rien. Le lien est donc modélisé
// explicitement — un **tuyau partagé** servi en file, à 200 Ko/s, avec 150 ms de latence. C'est le
// débit utile retenu par `pbm_api.jeu.budget.secondes_en_4g`, celui qu'on constate dans un train.
// Modèle sérialisé, donc **pessimiste** : une vraie 4G fait mieux.
//
// ⚠️ Les images servies ont le **poids réel** d'une variante de plateau (18 Kio, le plafond du
// budget) : servir un PNG de 200 octets rendrait le test vert en toutes circonstances.

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

/** Débit utile d'une 4G ordinaire, en octets par seconde — le même chiffre que côté serveur. */
const DEBIT_4G = 200 * 1024;

/** Latence d'un aller-retour en 4G. */
const LATENCE_4G_MS = 150;

/** Le poids réel d'une variante de plateau : le plafond déclaré par `pbm_api.jeu.budget`. */
const POIDS_VARIANTE_PLATEAU = 18 * 1024;

/**
 * Le temps dont on dispose. La mise en place, c'est au minimum poser un Pokémon de base de chaque
 * côté en lisant son plateau — jamais moins de quelques secondes. Six secondes est une borne
 * **prudente** : le modèle ci-dessus prédit ≈ 2,4 s pour 24 cartes, le reste couvre la variabilité
 * d'un agent de CI. Si ce test devient rouge, ce n'est pas la borne qu'il faut relever : c'est que
 * le plateau est redevenu trop lourd.
 */
const BUDGET_MISE_EN_PLACE_MS = 6000;

/** Un corps d'image du bon POIDS. Son contenu n'importe pas : c'est le temps qu'on mesure. */
const CORPS_IMAGE = Buffer.alloc(POIDS_VARIANTE_PLATEAU, 0x42);

function uniqueEmail(): string {
  return `e2e-prechargement-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Accorde le droit d'accès au jeu (D11) à un compte dédié, sans passer par l'inscription. */
function seedGameAccess(email: string): void {
  execFileSync("uv", ["run", "python", "scripts/seed_game_access_e2e.py", email, PASSWORD], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

/**
 * Un tuyau 4G **partagé** : les corps d'image sont servis l'un après l'autre, chacun occupant la
 * ligne le temps que ses octets prendraient réellement.
 *
 * Partagé et non par requête : six images téléchargées « en parallèle » sur un lien à 200 Ko/s
 * n'arrivent pas six fois plus vite. Un délai par requête aurait rendu le test optimiste, donc
 * inutile.
 */
function tuyau4g() {
  let libreA = 0;
  return async function servir(octets: number): Promise<void> {
    const maintenant = Date.now();
    const debut = Math.max(maintenant, libreA);
    const duree = (octets / DEBIT_4G) * 1000;
    libreA = debut + duree;
    const attente = debut - maintenant + duree + LATENCE_4G_MS;
    await new Promise((r) => setTimeout(r, Math.round(attente)));
  };
}

function renduPhoto(n: number) {
  return {
    origine: "photo",
    // Une URL distincte par carte : sinon le navigateur n'en chargerait qu'une, et le test
    // mesurerait un plateau d'une seule image.
    url: `/jeu/rendu/parties/simulee/photos/item-${n}?v=plateau`,
    url_zoom: `/jeu/rendu/parties/simulee/photos/item-${n}?v=zoom`,
    credit: null,
    url_repli: `/img/cards/c-${n}?size=low`,
  };
}

function pokemon(n: number) {
  return {
    cartes: [{ instance_id: `i-${n}`, ref: `ref-${n}`, rendu: renduPhoto(n) }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
}

/**
 * Une partie en **mise en place** : chaque camp a son actif et son banc, j'ai ma main de sept.
 *
 * **Dix-neuf** cartes porteuses d'image — mon actif + cinq de banc + sept en main (13), et en face
 * l'actif + cinq de banc (6). Sa main et ses récompenses restent des dos, donc zéro octet. C'est la
 * composition réelle du pire cas de mise en place ; les 24 que déclare
 * `budget.CARTES_MISE_EN_PLACE` sont ces 19 arrondis avec une marge.
 *
 * Le nombre est **rendu** avec la vue plutôt que recopié dans une assertion : une constante écrite
 * à la main se désynchronise du décor de test à la première carte ajoutée, et c'est exactement ce
 * qui a fait rougir la CI une fois.
 */
function vueMiseEnPlace() {
  let n = 0;
  const suivant = () => pokemon(++n);
  const main = Array.from({ length: 7 }, () => {
    n += 1;
    return { instance_id: `h-${n}`, ref: `main-${n}`, rendu: renduPhoto(n) };
  });
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [
      {
        id: "a",
        actif: suivant(),
        banc: [suivant(), suivant(), suivant(), suivant(), suivant()],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 41,
        recompenses_nombre: 6,
        main,
        recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
      },
      {
        id: "b",
        actif: suivant(),
        banc: [suivant(), suivant(), suivant(), suivant(), suivant()],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 39,
        recompenses_nombre: 6,
        main_nombre: 7,
      },
    ],
    tour: {
      joueur_actif: "a",
      numero: 1,
      phase: "mise_en_place",
      energie_posee: false,
      supporter_joue: false,
      retraite_faite: false,
    },
    stade: null,
    stade_proprietaire: null,
    terminee: false,
    vainqueur: null,
    raison_fin: null,
  };
}

/** Le nombre de cartes porteuses d'image du décor ci-dessus — **compté**, jamais supposé. */
function cartesAvecImage(vue: ReturnType<typeof vueMiseEnPlace>): number {
  const urls = new Set<string>();
  for (const joueur of vue.joueurs) {
    for (const p of [joueur.actif, ...(joueur.banc ?? [])]) {
      p?.cartes.forEach((c) => urls.add(c.rendu.url));
    }
    (joueur.main ?? []).forEach((c) => urls.add(c.rendu.url));
  }
  return urls.size;
}

async function login(page: Page, email: string): Promise<void> {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), "connexion du compte de test").toBeTruthy();
}

test.describe("Pré-chargement des images d'une partie en 4G simulée", () => {
  test("toutes les images du plateau arrivent avant la fin de la mise en place", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    const vue = vueMiseEnPlace();
    const servir = tuyau4g();
    /** Les requêtes d'image vues (chemin + paramètres) : la preuve qu'on charge le léger. */
    const demandees: string[] = [];

    // ⚠️ Les images sont servies AVEC leur en-tête de cache, comme en production (c'est ce que ce
    // lot ajoute aux deux routes d'images). Sans lui, chaque carte serait téléchargée **deux
    // fois** — une par le pré-chargeur, une par la balise `<img>` du plateau — et le test
    // mesurerait un gaspillage qui n'existe pas en vrai. Avec lui, le pré-chargement **remplit le
    // cache** et le plateau peint depuis le cache : c'est tout le mécanisme, et le compte de
    // requêtes ci-dessous le prouve.
    const entetes = { "cache-control": "private, max-age=60" };
    await page.route("**/jeu/rendu/parties/**", async (route) => {
      const adresse = new URL(route.request().url());
      demandees.push(adresse.pathname + adresse.search);
      await servir(CORPS_IMAGE.byteLength);
      await route.fulfill({ body: CORPS_IMAGE, contentType: "image/webp", headers: entetes });
    });
    await page.route("**/img/cards/**", async (route) => {
      await servir(CORPS_IMAGE.byteLength);
      await route.fulfill({ body: CORPS_IMAGE, contentType: "image/webp", headers: entetes });
    });
    await page.route("**/games/*/state", (route) =>
      route.fulfill({ json: { vue, evenements: [], numero: 1 } }),
    );
    await page.route("**/games/*/sync*", (route) =>
      route.fulfill({
        json: {
          type: "resync",
          numero: 1,
          depuis: 0,
          vue,
          evenements: [],
          statut: "en_cours",
          termine: false,
          vainqueur_user_id: null,
          raison_fin: null,
        },
      }),
    );
    await page.routeWebSocket(/\/ws/, (ws) => ws.close());

    await page.goto("/jeu/parties/partie-simulee");
    // Le chronomètre démarre quand le plateau est là : c'est à partir de ce moment que le joueur
    // commence sa mise en place, et donc le temps dont le pré-chargement dispose. Le poids du
    // JavaScript de l'application n'est pas l'objet de ce test.
    await expect(page.getByTestId("main-joueur")).toBeVisible();
    const depart = Date.now();

    // Le bandeau s'efface quand tout est arrivé : son effacement EST le signal « terminé », et il
    // est honnête (compté sur les images réellement reçues, échecs compris).
    await expect(page.getByTestId("prechargement-bandeau")).toBeHidden({
      timeout: BUDGET_MISE_EN_PLACE_MS,
    });
    const ecoule = Date.now() - depart;

    expect(
      ecoule,
      `pré-chargement en ${ecoule} ms (budget ${BUDGET_MISE_EN_PLACE_MS} ms en 4G simulée)`,
    ).toBeLessThan(BUDGET_MISE_EN_PLACE_MS);

    // Et ce sont bien les variantes LÉGÈRES qui ont été demandées, jamais le zoom : c'est tout
    // l'objet du dédoublement des variantes.
    for (const adresse of demandees) {
      expect(adresse, "le plateau ne doit jamais charger la variante de zoom").toContain(
        "v=plateau",
      );
    }

    // Le pré-chargement a couvert **toutes** les cartes visibles du décor, pas une carte
    // symbolique. Le nombre attendu est compté sur le décor lui-même : aucune constante à
    // maintenir, donc aucune dérive possible.
    const distinctes = new Set(demandees).size;
    expect(distinctes, "le pré-chargement doit couvrir toutes les cartes visibles").toBe(
      cartesAvecImage(vue),
    );

    // ⚠️ Le compte de requêtes est borné, mais **pas** à une par image, et il faut dire pourquoi :
    // le pré-chargeur (`new Image()`) et la balise `<img>` du plateau demandent la même URL
    // presque en même temps, avant que le cache ne soit rempli — le navigateur ne fusionne pas
    // toujours deux requêtes en vol venant de ces deux chemins. Mesuré en CI : 32 requêtes pour
    // 24 images, soit un tiers de recouvrement. Ce qui compte pour le joueur est le TEMPS, vérifié
    // plus haut ; cette borne-ci n'est là que pour attraper une régression franche (une image
    // redemandée à chaque rendu du plateau, par exemple).
    expect(
      demandees.length,
      `${demandees.length} requêtes pour ${distinctes} images distinctes`,
    ).toBeLessThan(distinctes * 2);
  });
});
