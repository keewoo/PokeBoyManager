import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";
import { extractTokenFromEmail, waitForEmail } from "./mailpit";

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

function uniqueEmail(): string {
  return `e2e-fiche-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Sème une carte possédée, avec historique de prix, état estimé, anecdotes et étude en jeu déjà
 * en cache (voir `apps/api/scripts/seed_card_fiche_e2e.py`) : aucune clé IA réelle ni wiki réel
 * disponible sur chimera, seule la fiche elle-même est exercée par le navigateur. Renvoie le
 * `card_id` créé. */
function seedCardFiche(email: string): string {
  const output = execFileSync(
    "uv",
    ["run", "python", "scripts/seed_card_fiche_e2e.py", email],
    { cwd: API_DIR, env: { ...process.env, DATABASE_URL }, encoding: "utf-8" }
  );
  return output.trim();
}

/** Compte + connexion par appels API directs (mêmes routes que le parcours réel testé par
 * `auth.spec.ts`) plutôt que remplir le formulaire d'inscription à l'écran : le nécessaire ici
 * est la fiche carte elle-même, pas de rejouer le formulaire d'inscription déjà couvert
 * ailleurs. `page.request` partage le pot de cookies du navigateur, la session posée par l'API
 * est donc bien celle utilisée par les appels `fetch` de la fiche. */
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

test.describe("Fiche carte (lot v4-fiche)", () => {
  test("affiche l'en-tête, la courbe de valeur et les onglets, conforme à la maquette", async ({
    page,
  }) => {
    const email = uniqueEmail();
    await registerAndLogin(page, email);
    const cardId = seedCardFiche(email);

    await page.goto(`/carte/${cardId}`);
    await expect(page.getByRole("heading", { name: "Dracaufeu-EX" })).toBeVisible();
    await expect(page.getByText("Écarlate et Violet").first()).toBeVisible();
    await expect(page.getByText("n° 1 de ta collection")).toBeVisible();
    // Valeur de la variante holo au relevé du jour (mission point 2, onglet Valeur par défaut).
    await expect(page.getByText("42,50 €")).toBeVisible();
    await page.waitForLoadState("networkidle");

    await page.screenshot({
      path: "../../docs/roadmap/comptes-rendus/assets/v4-fiche-onglet-valeur.png",
      fullPage: true,
    });

    await page.getByRole("tab", { name: "État" }).click();
    await expect(page.getByText("État estimé : Excellent")).toBeVisible();
    await expect(page.getByText("Centrage horizontal")).toBeVisible();

    await page.getByRole("tab", { name: "Histoire" }).click();
    await expect(page.getByText(/Distribuée en France/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Source" }).first()).toBeVisible();

    await page.getByRole("tab", { name: "En jeu" }).click();
    await expect(page.getByText("Explo-Combustion")).toBeVisible();
    await expect(page.getByText(/Quatre Énergies pour 150 dégâts/)).toBeVisible();

    await page.getByRole("tab", { name: "Mes exemplaires" }).click();
    const table = page.getByRole("table");
    await expect(table).toBeVisible();
    await expect(table.getByText("35,00 €")).toBeVisible();
    await page.waitForLoadState("networkidle");

    await page.screenshot({
      path: "../../docs/roadmap/comptes-rendus/assets/v4-fiche-onglet-exemplaires.png",
      fullPage: true,
    });

    // Bascule « Ma photo » (mission point 2) : l'exemplaire seedé a une photo, contrairement à
    // l'image officielle (aucun réseau vers TCGdex sur chimera, voir le script de seed).
    await page.getByRole("button", { name: "Ma photo" }).click();
    await expect(page.getByRole("img", { name: /Photo de Dracaufeu-EX/ })).toBeVisible();
  });

  test("un autre utilisateur ne voit aucun exemplaire ni la photo de la carte d'un autre", async ({
    page,
  }) => {
    const ownerEmail = uniqueEmail();
    const otherEmail = uniqueEmail();

    await registerAndLogin(page, ownerEmail);
    const cardId = seedCardFiche(ownerEmail);

    await registerAndLogin(page, otherEmail);
    await page.goto(`/carte/${cardId}`);
    await expect(page.getByRole("heading", { name: "Dracaufeu-EX" })).toBeVisible();
    await expect(page.getByText("Ajoutée le")).toBeVisible();

    await page.getByRole("tab", { name: "Mes exemplaires" }).click();
    await expect(
      page.getByText("Tu ne possèdes aucun exemplaire de cette carte.")
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Ma photo" })).toBeDisabled();
  });
});
