import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

// Lot `j-plateau-layout`, critère : « toutes les zones sont atteignables sans défilement sur un écran
// de 390 px de large en paysage », et « le plateau se redessine sans perdre l'état lors d'une
// rotation ». On mesure le défilement exactement comme `responsive.spec.ts` (le scrollWidth/
// scrollHeight du document comparé à la fenêtre — pas une approximation visuelle), sur le téléphone
// d'un enfant tenu en paysage.
//
// La vue de partie est **simulée** par interception réseau (`page.route`) : ce test porte sur la
// DISPOSITION, pas sur le moteur de jeu ni sur la construction d'une partie jouable (autres lots).
// La forme injectée est exactement le contrat de `GET /games/{id}/state` (voir `lib/game/plateau.ts`).

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

// Paysage d'un petit téléphone (le critère cite 390 px de large en paysage) et son miroir portrait.
const PAYSAGE = { width: 844, height: 390 };
const PORTRAIT = { width: 390, height: 844 };

function uniqueEmail(): string {
  return `e2e-plateau-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
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
        defausse: [{ instance_id: "ad1", ref: "defausse-adverse" }],
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
    stade: { instance_id: "s1", ref: "stade-partage" },
    stade_proprietaire: "a",
    terminee: false,
    vainqueur: null,
    raison_fin: null,
  };
}

async function login(page: Page, email: string): Promise<void> {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), "connexion du compte de test").toBeTruthy();
}

/**
 * Intercepte les routes de partie pour servir la vue simulée, sans moteur ni partie réelle.
 *
 * `terminee: true` sert une partie **finie** : l'écran de fin (lot `j-partie-fin-ui`) se déclenche
 * alors, et on peut mesurer qu'il n'allonge pas la page. Les deux routes qu'il appelle
 * (`/recapitulatif` et la liste des parties) sont stubées ici aussi — sinon le panneau afficherait
 * son message d'erreur, et le test mesurerait autre chose que ce qu'il croit.
 */
async function stubPartie(page: Page, options: { terminee?: boolean } = {}): Promise<void> {
  const finie = options.terminee === true;
  const vue = { ...vueSimulee(), terminee: finie, raison_fin: finie ? "derniere_recompense" : null };
  if (finie) {
    await page.route("**/games/*/recapitulatif", (route) =>
      route.fulfill({
        json: {
          game_id: "simulee",
          statut: "terminee",
          raison_fin: "derniere_recompense",
          vainqueur_user_id: null,
          entrainement: false,
          coups: 42,
          tours: 7,
          debut: "2026-10-14T10:00:00+00:00",
          fin: "2026-10-14T10:07:12+00:00",
          duree_s: 432,
          joueurs: [0, 1].map((seat) => ({
            seat,
            user_id: `u${seat}`,
            pseudo: `Joueur ${seat}`,
            degats_infliges: 180,
            kos_infliges: 3,
            recompenses_prises: 6,
            cartes_jouees: 9,
            energies_attachees: 5,
            coups_joues: 21,
          })),
          meilleur_coup: { numero: 31, user_id: "u0", degats: 120, ko: true },
        },
      }),
    );
    await page.route(/\/games(\?.*)?$/, (route) => route.fulfill({ json: [] }));
  }
  await page.route("**/games/*/state", (route) =>
    route.fulfill({ json: { vue, evenements: [] } }),
  );
  await page.route("**/games/*/sync*", (route) =>
    route.fulfill({
      json: {
        type: "resync",
        numero: 4,
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
  // Le WebSocket se ferme aussitôt : le canal replie en interrogation (vue simulée ci-dessus), sans
  // immobiliser le test sur une vraie connexion.
  await page.routeWebSocket(/\/ws/, (ws) => ws.close());
}

async function assertNoScroll(page: Page, label: string): Promise<void> {
  const { scrollWidth, innerWidth, scrollHeight, innerHeight } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    scrollHeight: document.documentElement.scrollHeight,
    innerHeight: window.innerHeight,
  }));
  expect(
    scrollWidth,
    `${label} : défilement horizontal (scrollWidth=${scrollWidth} > innerWidth=${innerWidth})`,
  ).toBeLessThanOrEqual(innerWidth);
  expect(
    scrollHeight,
    `${label} : défilement vertical (scrollHeight=${scrollHeight} > innerHeight=${innerHeight})`,
  ).toBeLessThanOrEqual(innerHeight + 4);
}

test.describe("Plateau : toutes les zones sans défilement sur un téléphone en paysage", () => {
  test("390 px en paysage : aucune zone hors de l'écran, aucun défilement", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");

    const plateau = page.getByTestId("plateau");
    await expect(plateau).toBeVisible();

    // Les zones essentielles sont réellement dans la fenêtre (atteignables sans défiler).
    await expect(page.getByRole("button", { name: /Mon actif/ })).toBeInViewport();
    await expect(page.getByRole("button", { name: /Actif adverse/ })).toBeInViewport();
    await expect(page.getByTestId("main-joueur")).toBeInViewport();
    await expect(page.getByTestId("zone-publique-ma défausse")).toBeInViewport();

    await assertNoScroll(page, "plateau @ 844×390 paysage");
  });

  test("rotation : le plateau se redessine sans perdre l'état, et sans défilement", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();
    await expect(page.getByText("mon-actif")).toBeVisible();

    // Portrait puis retour paysage : l'état (la même partie, le même actif) survit à la rotation —
    // il n'est jamais reconstruit côté écran, seulement redessiné.
    await page.setViewportSize(PORTRAIT);
    await expect(page.getByTestId("plateau")).toBeVisible();
    await assertNoScroll(page, "plateau @ 390×844 portrait");

    await page.setViewportSize(PAYSAGE);
    await expect(page.getByTestId("plateau")).toBeVisible();
    await expect(page.getByText("mon-actif")).toBeVisible();
    await assertNoScroll(page, "plateau @ 844×390 après rotation");
  });
});

test.describe("Fin de partie : l'écran de fin n'allonge pas la page du plateau", () => {
  test("partie finie en paysage puis en portrait : aucun défilement", async ({ page }) => {
    // Le risque est connu de ce dépôt : un panneau ajouté en flux normal sur `/jeu/parties/{id}`
    // casse ce job alors que vitest et type-check restent verts. L'écran de fin est donc `fixed`,
    // avec son propre défilement interne — et c'est ici que ça se vérifie.
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page, { terminee: true });

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");

    await expect(page.getByTestId("fin-partie")).toBeVisible();
    await expect(page.getByTestId("fin-partie-recap")).toBeVisible();
    await assertNoScroll(page, "écran de fin @ 844×390 paysage");

    await page.setViewportSize(PORTRAIT);
    await expect(page.getByTestId("fin-partie")).toBeVisible();
    await assertNoScroll(page, "écran de fin @ 390×844 portrait");

    // Replié, le plateau reste regardable — et la page ne défile toujours pas.
    await page.getByTestId("fin-partie-replier").click();
    await expect(page.getByTestId("plateau")).toBeVisible();
    await assertNoScroll(page, "plateau derrière l'écran de fin replié");
  });
});
