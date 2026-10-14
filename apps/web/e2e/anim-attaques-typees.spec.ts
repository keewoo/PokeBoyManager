import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page, type TestInfo } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";
import { SPECS, TYPE_LE_PLUS_LOURD } from "../src/lib/game/anim-types";

/**
 * Lot `j-anim-attaques-typees`, critère d'acceptation n°4 : **le plancher d'images par seconde est
 * tenu avec l'effet le plus lourd**.
 *
 * C'est le seul des quatre critères qui ne peut pas se vérifier sans navigateur : les trois autres
 * sont tenus par construction et gardés par `src/lib/game/anim-types.test.ts`,
 * `src/__tests__/anim-types-css-garde.test.ts` et `src/components/game/board-card.test.tsx`. Celui-ci
 * se **mesure**, sur le même appareil de référence que `anim-fluidite.spec.ts` — un téléphone
 * d'entrée de gamme, modélisé par une fenêtre de 844×390 et un bridage processeur ×4.
 *
 * Ce qu'on mesure ici que `anim-fluidite.spec.ts` ne mesure pas : ses coups ne portent **aucun
 * type** d'attaque (ils datent d'avant ce lot), donc aucun effet typé ne s'y joue. Ici les coups
 * portent le type **le plus lourd de la table** — calculé, pas choisi (`TYPE_LE_PLUS_LOURD`) : le
 * jour où un type plus chargé est ajouté, c'est lui qui est mesuré, sans que personne n'ait à y
 * penser.
 *
 * Et une attaque **avec faiblesse** par-dessus, pour que l'intensité soit au maximum : c'est le
 * palier `fort`, celui qui rend le plus de particules et la plus grande amplitude.
 *
 * Le test exige aussi que **les compteurs de dégâts restent visibles** pendant l'effet. C'est le
 * risque nommé par le lot, et il ne se vérifie complètement que dans un vrai rendu : l'ordre de DOM
 * est gardé en jsdom, mais seul le navigateur dit si le chiffre est réellement à l'écran.
 */

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

/** L'appareil de référence : un petit téléphone tenu en paysage (même que `anim-fluidite`). */
const REFERENCE = { width: 844, height: 390 };
/** Bridage processeur simulant un appareil d'entrée de gamme. */
const BRIDAGE_CPU = 4;
/** Le plancher annoncé par le socle (`PLANCHER_FPS` de `src/lib/game/animations.ts`). */
const PLANCHER_FPS = 30;
/** En dessous de cet échantillon, la fenêtre de mesure est trop courte pour conclure. */
const CADRES_MIN = 20;

/** La clé CSS du type le plus lourd : c'est elle que porte `data-fx` dans le DOM. */
const CLE_LA_PLUS_LOURDE = SPECS[TYPE_LE_PLUS_LOURD]!.cle;

function uniqueEmail(): string {
  return `e2e-fx-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Accorde le droit d'accès au jeu (D11) à un compte dédié, sans passer par l'inscription. */
function seedGameAccess(email: string): void {
  execFileSync("uv", ["run", "python", "scripts/seed_game_access_e2e.py", email, PASSWORD], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

/** Un Pokémon en jeu, forme `pbm_game.state.projection`. */
function pokemon(ref: string, degats = 0) {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref }],
    energies: [{ instance_id: `e-${ref}`, ref: "energie" }],
    outil: null,
    compteurs_degats: degats,
    etats_speciaux: [],
    orientation: "normale",
    pv_restants: 120 - degats,
    pv_max: 120,
  };
}

/** La vue projetée d'une partie : l'Actif adverse porte déjà des dégâts, qu'on veut voir rester. */
function vueSimulee() {
  const banc = (prefixe: string) => [0, 1, 2].map((n) => pokemon(`${prefixe}-banc${n}`));
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [
      {
        id: "a",
        actif: pokemon("mon-actif"),
        banc: banc("moi"),
        defausse: [{ instance_id: "md1", ref: "ma-defausse" }],
        zone_perdue: [],
        pioche_nombre: 41,
        recompenses_nombre: 6,
        main: [0, 1, 2, 3, 4].map((n) => ({ instance_id: `h${n}`, ref: `main-${n}` })),
        recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
      },
      {
        id: "b",
        actif: pokemon("actif-adverse", 90),
        banc: banc("adv"),
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 39,
        recompenses_nombre: 5,
        main_nombre: 6,
      },
    ],
    tour: {
      joueur_actif: "a",
      numero: 4,
      phase: "principale",
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

/**
 * Trois attaques du type le plus lourd, **toutes avec faiblesse** : intensité maximale, donc le
 * maximum de particules et la plus grande amplitude. L'ordre des événements est celui du moteur —
 * `degats` AVANT `attaque_declaree`, qui porte le type.
 *
 * ⚠️ **Trois** et pas cinq, et c'est volontaire : chaque coup porte DEUX événements animés, donc
 * trois coups font six animations pour 2,34 s — juste sous le seuil de rattrapage du socle
 * (`SEUIL_RATTRAPAGE` = 6, `BUDGET_RATTRAPAGE` = 2,4 s). Au-delà, la file **résume** au lieu de
 * tout rejouer : on mesurerait alors l'animation de résumé, pas les effets typés. C'est le même
 * raisonnement que `anim-fluidite.spec.ts`, avec deux fois plus d'événements par coup.
 */
function coupsTypes() {
  return [1, 2, 3].map((n) => ({
    numero: n,
    evenements: [
      {
        type: "degats",
        donnees: {
          cible: "i-actif-adverse",
          degats: 200,
          compteurs: 20,
          detail: "100 base, ×2 faiblesse = 200",
          au_banc: false,
          faiblesse: true,
          resistance: false,
        },
      },
      {
        type: "attaque_declaree",
        donnees: { joueur: "b", degats: 200, type: TYPE_LE_PLUS_LOURD },
      },
    ],
  }));
}

async function login(page: Page, email: string): Promise<void> {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), "connexion du compte de test").toBeTruthy();
}

/** Joint une capture au rapport Playwright — c'est elle qu'on publie depuis la CI. */
async function capturer(page: Page, info: TestInfo, nom: string, pleinePage = false) {
  await info.attach(nom, {
    body: await page.screenshot({ fullPage: pleinePage }),
    contentType: "image/png",
  });
}

/** Prépare une partie simulée qui livre `coups` à la resynchronisation, derrière un portillon. */
async function partieSimulee(page: Page, coups: unknown[]): Promise<() => void> {
  const vue = vueSimulee();
  await page.route("**/games/*/state", (route) =>
    route.fulfill({ json: { vue, evenements: [], numero: 0 } }),
  );
  let ouvrir: () => void = () => {};
  const portillon = new Promise<void>((r) => {
    ouvrir = r;
  });
  await page.route("**/games/*/sync*", async (route) => {
    await portillon;
    await route.fulfill({
      json: {
        type: "resync",
        numero: coups.length + 1,
        depuis: 0,
        vue,
        evenements: coups,
        statut: "en_cours",
        termine: false,
        vainqueur_user_id: null,
        raison_fin: null,
      },
    });
  });
  // Le WebSocket se ferme aussitôt : le canal replie en interrogation HTTP (ci-dessus).
  await page.routeWebSocket(/\/ws/, (ws) => ws.close());
  return ouvrir;
}

test.describe("Effets typés : le plancher d'images par seconde avec l'effet le plus lourd", () => {
  test(`tient ${PLANCHER_FPS} images/s avec « ${CLE_LA_PLUS_LOURDE} » à pleine intensité`, async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    const ouvrir = await partieSimulee(page, coupsTypes());
    await page.setViewportSize(REFERENCE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Le bridage ne s'applique qu'APRÈS le chargement : on mesure l'animation sur un appareil lent,
    // pas le temps d'hydratation de Next.
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: BRIDAGE_CPU });

    await page.evaluate(() => {
      const w = window as unknown as { __cadres: number; __depart: number };
      w.__cadres = 0;
      w.__depart = performance.now();
      const boucle = () => {
        w.__cadres += 1;
        requestAnimationFrame(boucle);
      };
      requestAnimationFrame(boucle);
    });

    ouvrir();

    const fx = page.getByTestId("fx-typee");
    // Garde-fou : si aucun effet TYPÉ n'apparaissait, on ne veut pas d'un verdict sur une fenêtre
    // vide — c'est exactement ce qui rendrait ce test vert sans rien mesurer. On vérifie aussi que
    // c'est bien le type le plus lourd, à pleine intensité : sinon on mesurerait un effet léger en
    // croyant mesurer le pire cas.
    await expect(fx.first(), "l'effet typé doit apparaître").toBeVisible({ timeout: 10_000 });
    await expect(fx.first()).toHaveAttribute("data-fx", CLE_LA_PLUS_LOURDE);
    await expect(fx.first()).toHaveAttribute("data-palier", "fort");
    await expect(fx.first()).toHaveAttribute("data-renforce", "");

    // ⚠️ On attend la fin de la RAFALE ENTIÈRE (la couche du socle), pas la fin du premier effet
    // typé. Un effet dure 420 ms ; s'arrêter là mesurerait une fenêtre de quelques dizaines de
    // cadres dominée par le chargement de la page — un chiffre instable, qui passerait ou
    // échouerait au hasard (mesuré : il faisait les deux). La fenêtre est donc **exactement** celle
    // de `anim-fluidite.spec.ts`, ce qui rend les deux chiffres directement comparables : c'est de
    // leur écart qu'on apprend ce que l'effet typé coûte vraiment.
    await page.getByTestId("anim-couche").waitFor({ state: "detached", timeout: 20_000 });

    const { cadres, duree } = await page.evaluate(() => {
      const w = window as unknown as { __cadres: number; __depart: number };
      return { cadres: w.__cadres, duree: performance.now() - w.__depart };
    });

    const fps = (cadres / duree) * 1000;
    // Le chiffre est publié dans le journal de la CI : c'est la mesure, pas une intention.
    console.log(
      `[j-anim-attaques-typees] fluidité mesurée avec l'effet le plus lourd (« ${CLE_LA_PLUS_LOURDE} », palier fort) : ${fps.toFixed(1)} images/s (${cadres} cadres en ${duree.toFixed(0)} ms, 844×390, CPU ×${BRIDAGE_CPU})`,
    );

    expect(cadres, "échantillon de cadres trop faible pour conclure").toBeGreaterThanOrEqual(
      CADRES_MIN,
    );
    expect(
      fps,
      `plancher non tenu avec l'effet le plus lourd : ${fps.toFixed(1)} images/s mesurées, ${PLANCHER_FPS} attendues`,
    ).toBeGreaterThanOrEqual(PLANCHER_FPS);
  });

  test("les compteurs de dégâts restent visibles PENDANT l'effet", async ({ page }, info) => {
    // Le risque nommé par le lot : « l'une d'elles finira par cacher un compteur de dégâts au
    // moment décisif ». L'ordre de DOM est gardé en jsdom (`board-card.test.tsx`) ; seul un vrai
    // rendu dit si le chiffre est effectivement à l'écran, par-dessus les couches de l'effet.
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    const ouvrir = await partieSimulee(page, coupsTypes());
    await page.setViewportSize(REFERENCE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();
    ouvrir();

    const fx = page.getByTestId("fx-typee");
    await expect(fx.first()).toBeVisible({ timeout: 10_000 });

    // L'Actif adverse porte 90 dégâts dans la vue : son compteur doit rester lisible et dans la
    // fenêtre, pendant que l'effet se joue sur cette même carte.
    // Sélecteur sur l'attribut plutôt que `getByLabel` : l'étiquette est portée par un `<span>`
    // (un jeton posé sur la carte), pas par un champ de formulaire.
    const compteur = page.locator('[aria-label*="90 dégâts"]').first();
    await expect(compteur).toBeVisible();
    await expect(compteur).toBeInViewport();

    // Capture jointe au rapport Playwright : c'est la preuve visuelle du compte rendu du lot.
    await capturer(page, info, "fx-typee-plateau");
  });

  test("la galerie montre les onze types, et sert de preuve de recette", async ({ page }, info) => {
    // Elle existe pour la validation de JF et d'Aymeric (exigence du lot) : on vérifie ici qu'elle
    // s'ouvre vraiment et qu'aucun type n'y manque, puis on en joint une capture.
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/jeu/effets");
    await expect(page.getByTestId("fx-galerie")).toBeVisible({ timeout: 15_000 });

    for (const spec of Object.values(SPECS)) {
      await expect(
        page.getByTestId(`fx-demo-${spec.cle}`),
        `aucune vignette pour ${spec.libelle}`,
      ).toBeVisible();
    }

    await page.getByTestId("fx-situation-violente").click();
    await capturer(page, info, "fx-galerie-grosse-attaque", true);
    await page.getByTestId("fx-situation-echec").click();
    await capturer(page, info, "fx-galerie-attaque-ratee", true);
  });
});
