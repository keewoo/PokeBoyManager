import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

// Emotes prédéfinies en partie (lot `j-echanges-emotes`, décision DJ10), **dans un vrai navigateur**.
//
// Trois choses qu'aucun test unitaire ne prouve, parce qu'elles n'existent qu'une fois la page
// assemblée :
//
// 1. **aucune saisie de texte libre** sur le plateau — on compte les `input`/`textarea` du DOM
//    rendu, palette ouverte comprise. C'est le critère n° 1 du lot, et le risque nommé (« ajouter
//    juste un petit chat plus tard ») ;
// 2. **la palette n'allonge pas la page** : `/jeu/parties/{id}` ne tolère aucun défilement, et ce
//    dépôt a déjà payé un panneau posé en flux normal — invisible en vitest comme en `tsc` ;
// 3. **le code part bien par le canal temps réel**, et une emote poussée par le serveur s'affiche
//    en clair. Le WebSocket est ici un vrai socket (intercepté par `routeWebSocket`), donc le
//    canal passe réellement en « direct » — l'état sans lequel la palette reste fermée.
//
// La vue de partie est **simulée** par interception réseau, comme `plateau-responsive.spec.ts` :
// ce test porte sur les emotes, pas sur le moteur.

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

const PAYSAGE = { width: 844, height: 390 };

function uniqueEmail(): string {
  return `e2e-emote-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Accorde le droit d'accès au jeu (D11) à un compte dédié, sans passer par l'inscription. */
function seedGameAccess(email: string): void {
  execFileSync("uv", ["run", "python", "scripts/seed_game_access_e2e.py", email, PASSWORD], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

async function login(page: Page, email: string): Promise<void> {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), "connexion du compte de test").toBeTruthy();
}

/** Un Pokémon en jeu, forme `pbm_game.state.projection`. */
function pokemon(ref: string) {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref }],
    energies: [],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
}

/** La vue projetée d'une partie en cours, minimale mais conforme au contrat de `/games/{id}/state`. */
function vueSimulee() {
  return {
    schema_version: 1,
    pour: "a",
    joueurs: [
      {
        id: "a",
        actif: pokemon("mon-actif"),
        banc: [],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 41,
        recompenses_nombre: 6,
        main: [{ instance_id: "h0", ref: "main-0" }],
        recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
      },
      {
        id: "b",
        actif: pokemon("actif-adverse"),
        banc: [],
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 39,
        recompenses_nombre: 6,
        main_nombre: 6,
      },
    ],
    actions_legales: [],
    actions_refusees: [],
    demandes: [],
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
 * Intercepte la partie **et** le WebSocket. Le socket reste ouvert et répond à la souscription par
 * une resynchronisation : c'est la seule façon d'amener le canal en « direct », l'état dans lequel
 * la palette d'emotes s'ouvre. Les messages du client sont capturés dans le tableau renvoyé.
 */
async function stubPartieEnDirect(page: Page) {
  const vue = vueSimulee();
  const envoyes: Record<string, unknown>[] = [];
  const serveur: { pousser: ((charge: unknown) => void) | null } = { pousser: null };

  await page.route("**/games/*/state", (route) =>
    route.fulfill({ json: { vue, evenements: [], numero: 4 } }),
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

  await page.routeWebSocket(/\/ws/, (ws) => {
    const resync = {
      type: "resync",
      numero: 4,
      depuis: 0,
      vue,
      evenements: [],
      statut: "en_cours",
      termine: false,
      vainqueur_user_id: null,
      raison_fin: null,
    };
    serveur.pousser = (charge: unknown) => ws.send(JSON.stringify(charge));
    ws.send(JSON.stringify(resync));
    ws.onMessage((message) => {
      envoyes.push(JSON.parse(String(message)) as Record<string, unknown>);
    });
  });

  return { envoyes, serveur };
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

test.describe("Emotes en partie (DJ10) : se parler sans chat libre", () => {
  test("la palette envoie un code, jamais du texte, et n'allonge pas la page", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    const { envoyes, serveur } = await stubPartieEnDirect(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Le canal est en direct : la palette s'ouvre (hors direct, le bouton est désactivé).
    const ouvrir = page.getByTestId("emotes-ouvrir");
    await expect(ouvrir).toBeEnabled();
    await ouvrir.click();

    const palette = page.getByTestId("emotes-palette");
    await expect(palette).toBeVisible();
    await expect(palette.getByRole("button")).toHaveCount(10);

    // ⛔ Le critère n° 1 du lot, mesuré sur le DOM réel, palette ouverte : rien pour écrire.
    expect(
      await page.locator("input, textarea, [contenteditable='true']").count(),
      "aucun champ de saisie ne doit exister sur le plateau (DJ10 : jamais de texte libre)",
    ).toBe(0);

    // La palette est hors flux : ouverte, elle ne doit pas créer un défilement sur un téléphone.
    await assertNoScroll(page, "plateau @ 844×390, palette d'emotes ouverte");

    // Ce qui part sur le canal est un **code**, et rien d'autre.
    await page.getByTestId("emote-bien_joue").click();
    await expect
      .poll(() => envoyes.filter((m) => m.type === "emote").length, { timeout: 5000 })
      .toBe(1);
    expect(envoyes.find((m) => m.type === "emote")).toEqual({
      type: "emote",
      code: "bien_joue",
    });

    // Et une emote poussée par le serveur s'affiche en clair (pas son code).
    serveur.pousser?.({ type: "emote", code: "ton_tour", de: "adversaire" });
    await expect(page.getByTestId("emote-bulle")).toHaveText(/À toi de jouer/);
  });

  test("couper les emotes est immédiat, et mémorisé après un rechargement", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartieEnDirect(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("emotes-ouvrir")).toBeVisible();

    await page.getByTestId("emotes-interrupteur").click();

    // Immédiat : la palette disparaît sans rechargement.
    await expect(page.getByTestId("emotes-ouvrir")).toHaveCount(0);
    await expect(page.getByTestId("emotes-interrupteur")).toHaveText(/coupées/);

    // Mémorisé : le réglage est écrit côté compte, pas dans cet onglet — un F5 le retrouve.
    await page.reload();
    await expect(page.getByTestId("emotes-interrupteur")).toHaveText(/coupées/);
    await expect(page.getByTestId("emotes-ouvrir")).toHaveCount(0);
    await assertNoScroll(page, "plateau @ 844×390, emotes coupées");
  });
});
