import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

/**
 * Lot `j-anim-socle`, critère d'acceptation n°3 : **le plancher d'images par seconde est tenu sur
 * l'appareil de référence**.
 *
 * L'« appareil de référence » est nommé, pas sous-entendu : un téléphone d'entrée de gamme, modélisé
 * ici par une fenêtre de 844×390 (le téléphone d'un enfant tenu en paysage, comme
 * `plateau-responsive.spec.ts`) et un **bridage processeur ×4** (`Emulation.setCPUThrottlingRate`),
 * qui est la façon dont Chromium simule un appareil lent. Le plancher est `PLANCHER_FPS`
 * (`src/lib/game/animations.ts`), soit 30 images par seconde.
 *
 * La mesure compte les **cadres réellement rendus** (`requestAnimationFrame`) pendant que les
 * animations se jouent, et rapporte le chiffre obtenu. Deux garde-fous contre une mesure qui
 * mentirait :
 *
 * - le test **exige** d'avoir vu la couche d'animation apparaître : si rien ne s'animait, il
 *   échouerait au lieu de passer sur une fenêtre vide ;
 * - il **exige** un échantillon minimum de cadres : une fenêtre trop courte ne vaut pas verdict.
 *
 * Ce que ce test mesure, `src/__tests__/anim-css-garde.test.ts` le garde par construction (seules
 * `transform` et `opacity` sont animées) et `src/lib/game/animations.test.ts` par invariant (une
 * seule animation à la fois). Les trois disent la même chose de trois façons : c'est voulu — une
 * mesure seule ne dit jamais pourquoi elle tombe.
 */

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

/** L'appareil de référence : un petit téléphone tenu en paysage. */
const REFERENCE = { width: 844, height: 390 };
/** Bridage processeur simulant un appareil d'entrée de gamme. */
const BRIDAGE_CPU = 4;
/** Le plancher annoncé par le socle (`PLANCHER_FPS`). */
const PLANCHER_FPS = 30;
/** En dessous de cet échantillon, la fenêtre de mesure est trop courte pour conclure. */
const CADRES_MIN = 20;

function uniqueEmail(): string {
  return `e2e-anim-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Accorde le droit d'accès au jeu (D11) à un compte dédié, sans passer par l'inscription (débit). */
function seedGameAccess(email: string): void {
  execFileSync("uv", ["run", "python", "scripts/seed_game_access_e2e.py", email, PASSWORD], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

/** Un Pokémon en jeu, forme `pbm_game.state.projection`. */
function pokemon(ref: string) {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref }],
    energies: [{ instance_id: `e-${ref}`, ref: "energie" }],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
}

/** La vue projetée d'une partie, telle que `GET /games/{id}/state` la renverrait. */
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
        actif: pokemon("actif-adverse"),
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
 * Cinq coups qui s'animent à la suite : 2,2 s d'animation continue, juste en dessous du budget de
 * rattrapage (`BUDGET_RATTRAPAGE`, 2,4 s) — on veut mesurer l'animation réelle, pas son résumé.
 */
function coupsAnimes() {
  const types = [
    ["attaque_declaree", { joueur: "a", pokemon: "i-mon-actif", attaque: "Éclair" }],
    ["degats", { cible: "i-actif-adverse", valeur: 60 }],
    ["energie_attachee", { joueur: "a", pokemon: "i-mon-actif" }],
    ["evolution", { joueur: "a", base: "i-moi-banc0" }],
    ["ko", { cible: "i-actif-adverse" }],
  ] as const;
  return types.map(([type, donnees], i) => ({
    numero: i + 1,
    evenements: [{ type, donnees }],
  }));
}

async function login(page: Page, email: string): Promise<void> {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), "connexion du compte de test").toBeTruthy();
}

test.describe("Animations : le plancher d'images par seconde sur l'appareil de référence", () => {
  test(`tient ${PLANCHER_FPS} images/s à 844×390 avec un processeur bridé ×${BRIDAGE_CPU}`, async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    const vue = vueSimulee();
    // La vue initiale ne porte aucun coup : les animations ne partiront qu'au signal du test.
    await page.route("**/games/*/state", (route) =>
      route.fulfill({ json: { vue, evenements: [], numero: 0 } }),
    );

    // Portillon : la resynchronisation (qui livre les cinq coups) attend que la mesure soit armée.
    let ouvrir: () => void = () => {};
    const portillon = new Promise<void>((r) => {
      ouvrir = r;
    });
    await page.route("**/games/*/sync*", async (route) => {
      await portillon;
      await route.fulfill({
        json: {
          type: "resync",
          numero: 6,
          depuis: 0,
          vue,
          evenements: coupsAnimes(),
          statut: "en_cours",
          termine: false,
          vainqueur_user_id: null,
          raison_fin: null,
        },
      });
    });
    // Le WebSocket se ferme aussitôt : le canal replie en interrogation HTTP (ci-dessus).
    await page.routeWebSocket(/\/ws/, (ws) => ws.close());

    await page.setViewportSize(REFERENCE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Le bridage ne s'applique qu'APRÈS le chargement : on mesure l'animation sur un appareil lent,
    // pas le temps d'hydratation de Next (qui n'est pas l'objet de ce critère).
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: BRIDAGE_CPU });

    // Compteur de cadres armé DANS la page, avant que la moindre animation ne démarre.
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

    const couche = page.getByTestId("anim-couche");
    // Garde-fou : si rien ne s'animait, on ne veut PAS d'un verdict sur une fenêtre vide.
    await expect(couche, "la couche d'animation doit apparaître").toBeVisible({ timeout: 10_000 });
    // La rafale dure environ 2,2 s ; on attend sa fin complète.
    await couche.waitFor({ state: "detached", timeout: 15_000 });

    const { cadres, duree } = await page.evaluate(() => {
      const w = window as unknown as { __cadres: number; __depart: number };
      return { cadres: w.__cadres, duree: performance.now() - w.__depart };
    });

    const fps = (cadres / duree) * 1000;
    // Le chiffre est publié dans le journal de la CI : c'est la mesure, pas une intention.
    console.log(
      `[j-anim-socle] fluidité mesurée : ${fps.toFixed(1)} images/s (${cadres} cadres en ${duree.toFixed(0)} ms, 844×390, CPU ×${BRIDAGE_CPU})`,
    );

    expect(cadres, "échantillon de cadres trop faible pour conclure").toBeGreaterThanOrEqual(
      CADRES_MIN,
    );
    expect(
      fps,
      `plancher du socle non tenu : ${fps.toFixed(1)} images/s mesurées, ${PLANCHER_FPS} attendues sur l'appareil de référence`,
    ).toBeGreaterThanOrEqual(PLANCHER_FPS);
  });

  test("l'animation ne retient jamais le plateau : le bouton « passer » la termine", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    const vue = vueSimulee();
    await page.route("**/games/*/state", (route) =>
      route.fulfill({ json: { vue, evenements: [], numero: 0 } }),
    );
    await page.route("**/games/*/sync*", (route) =>
      route.fulfill({
        json: {
          type: "resync",
          numero: 6,
          depuis: 0,
          vue,
          evenements: coupsAnimes(),
          statut: "en_cours",
          termine: false,
          vainqueur_user_id: null,
          raison_fin: null,
        },
      }),
    );
    await page.routeWebSocket(/\/ws/, (ws) => ws.close());

    await page.setViewportSize(REFERENCE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();
    await expect(page.getByTestId("anim-sauter")).toBeVisible({ timeout: 10_000 });

    // Le plateau reste lisible pendant l'animation, et quatre clics suffisent à tout passer :
    // l'écran ne se met jamais en travers.
    for (let i = 0; i < 5; i += 1) {
      const bouton = page.getByTestId("anim-sauter");
      if (!(await bouton.isVisible())) break;
      await bouton.click();
    }
    await expect(page.getByTestId("anim-couche")).toHaveCount(0, { timeout: 10_000 });
    // Et le plateau n'a pas bougé d'un pixel : aucune zone n'a disparu, aucun défilement.
    await expect(page.getByTestId("main-joueur")).toBeInViewport();
  });
});
