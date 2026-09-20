import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";
import { extractTokenFromEmail, waitForEmail } from "./mailpit";

// Mission `pbm-front-accueil`, point 2 : plus de défilement horizontal sur aucune page livrée,
// à aucune des quatre largeurs demandées, et la barre de navigation se replie en menu sous
// 640px (point 3). `document.documentElement.scrollWidth <= window.innerWidth` est la mesure
// citée par la mission elle-même — pas une approximation visuelle.

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

const WIDTHS = [320, 390, 768, 1280];
const HEIGHT = 900;

function uniqueEmail(): string {
  return `e2e-responsive-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Même patron que `card-detail.spec.ts` : sème une carte possédée pour avoir une fiche réelle
 * à mesurer, sans dépendre d'un pipeline de reconnaissance (aucune clé IA réelle sur chimera). */
function seedCardFiche(email: string): string {
  const output = execFileSync(
    "uv",
    ["run", "python", "scripts/seed_card_fiche_e2e.py", email],
    { cwd: API_DIR, env: { ...process.env, DATABASE_URL }, encoding: "utf-8" }
  );
  return output.trim();
}

async function registerAndLogin(page: Page, email: string): Promise<void> {
  await page.request.post(`${API_BASE_URL}/auth/register`, {
    data: {
      email,
      password: PASSWORD,
      last_name: "Dresseur",
      birth_date: "2000-01-01",
      accept_terms: true,
    },
  });
  const emailBody = await waitForEmail(email);
  const token = extractTokenFromEmail(emailBody);
  await page.request.post(`${API_BASE_URL}/auth/verify-email`, { data: { token } });
  await page.request.post(`${API_BASE_URL}/auth/login`, { data: { email, password: PASSWORD } });
}

async function assertNoHorizontalScroll(page: Page, label: string): Promise<void> {
  const { scrollWidth, innerWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
  }));
  expect(
    scrollWidth,
    `${label} : défilement horizontal (scrollWidth=${scrollWidth} > innerWidth=${innerWidth})`
  ).toBeLessThanOrEqual(innerWidth);
}

async function checkPagesAtAllWidths(page: Page, paths: string[]): Promise<void> {
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: HEIGHT });
    for (const path of paths) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await assertNoHorizontalScroll(page, `${path} @ ${width}px`);
    }
  }
}

test.describe("Aucun défilement horizontal, à 320/390/768/1280px", () => {
  test("pages publiques : accueil, inscription, connexion", async ({ page }) => {
    await checkPagesAtAllWidths(page, ["/", "/inscription", "/connexion"]);
  });

  test("pages privées : ajouter, collection, fiche carte, profil", async ({ page }) => {
    const email = uniqueEmail();
    await registerAndLogin(page, email);
    const cardId = seedCardFiche(email);

    await checkPagesAtAllWidths(page, ["/ajouter", "/collection", `/carte/${cardId}`, "/profil"]);
  });
});

test.describe("La navigation se replie en menu sous 640px (mission point 3)", () => {
  test("le bouton de menu apparaît sur téléphone et disparaît en desktop", async ({ page }) => {
    await page.goto("/");

    await page.setViewportSize({ width: 390, height: HEIGHT });
    await expect(page.getByRole("button", { name: "Ouvrir le menu" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Présentation" })).not.toBeVisible();

    await page.getByRole("button", { name: "Ouvrir le menu" }).click();
    await expect(page.getByRole("link", { name: "Présentation" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Connexion" })).toBeVisible();

    await page.setViewportSize({ width: 1280, height: HEIGHT });
    await expect(page.getByRole("button", { name: /ouvrir le menu|fermer le menu/i })).not.toBeVisible();
    await expect(page.getByRole("link", { name: "Présentation" })).toBeVisible();
  });
});
