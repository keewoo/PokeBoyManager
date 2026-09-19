import { test, expect } from "@playwright/test";

import { extractTokenFromEmail, waitForEmail } from "./mailpit";

const PASSWORD = "un-mot-de-passe-tres-solide";

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

test.describe("Parcours inscription → vérification → connexion", () => {
  test("un visiteur crée son compte, vérifie son e-mail puis se connecte", async ({ page }) => {
    const email = uniqueEmail();

    await page.goto("/inscription");
    await page.getByLabel(/^nom$/i).fill("Dresseur");
    await page.getByLabel(/date de naissance/i).fill("2000-01-01");
    await page.getByLabel(/e-mail/i).fill(email);
    await page.getByLabel(/mot de passe/i).fill(PASSWORD);
    await page.getByLabel(/j'accepte les conditions/i).check();
    await page.getByRole("button", { name: /créer mon espace/i }).click();

    await expect(page.getByText(/vérifie ta boîte mail/i)).toBeVisible();

    const emailBody = await waitForEmail(email);
    const token = extractTokenFromEmail(emailBody);

    await page.goto(`/verifier?token=${token}`);
    await expect(page.getByText(/adresse e-mail est vérifiée/i)).toBeVisible();

    await page.getByRole("link", { name: /se connecter/i }).click();
    await expect(page).toHaveURL(/\/connexion$/);

    await page.getByLabel(/e-mail/i).fill(email);
    await page.getByLabel(/mot de passe/i).fill(PASSWORD);
    await page.getByRole("button", { name: /se connecter/i }).click();

    // La connexion pose le cookie de session : la garde de route laisse alors passer une
    // page privée directement (sans repasser par /connexion).
    await page.waitForURL("/");
    const cookies = await page.context().cookies();
    expect(cookies.some((cookie) => cookie.name === "pbm_session")).toBe(true);

    await page.goto("/profil");
    await expect(page).toHaveURL(/\/profil$/);
  });

  test("une page privée redirige vers /connexion?next=... sans session", async ({ page }) => {
    await page.goto("/collection");
    await expect(page).toHaveURL(/\/connexion\?next=%2Fcollection$/);
  });

  test("un mot de passe oublié renvoie le même écran, e-mail connu ou non", async ({ page }) => {
    await page.goto("/mot-de-passe-oublie");
    await page.getByLabel(/e-mail/i).fill(`inconnu-${Date.now()}@example.fr`);
    await page.getByRole("button", { name: /envoyer le lien/i }).click();

    await expect(page.getByText(/si un compte existe pour cette adresse/i)).toBeVisible();
  });
});
