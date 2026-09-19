import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect } from "@playwright/test";

import { extractTokenFromEmail, waitForEmail } from "./mailpit";

const PASSWORD = "un-mot-de-passe-tres-solide";
// `cwd` du run Playwright = `apps/web` (voir `package.json`) : pas de `__dirname` disponible en
// ESM, et inutile ici puisque le répertoire de travail est déjà connu.
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

function uniqueEmail(): string {
  return `e2e-validation-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Sème un envoi déjà « identifié » pour cet utilisateur (voir
 * `apps/api/scripts/seed_validation_e2e.py`) : aucune clé IA réelle disponible sur chimera, le
 * pipeline de reconnaissance réel (OpenCV + IA) n'est donc pas exercé par ce test — seul l'écran
 * de validation lui-même l'est, contre un état déjà identifié. Renvoie l'`upload_id` créé. */
function seedValidationUpload(email: string): string {
  const output = execFileSync(
    "uv",
    ["run", "python", "scripts/seed_validation_e2e.py", email],
    { cwd: API_DIR, env: { ...process.env, DATABASE_URL }, encoding: "utf-8" }
  );
  return output.trim();
}

test.describe("Écran de validation (lot v3-validation)", () => {
  test("affiche la carte détectée et la valide dans la collection", async ({ page }) => {
    const email = uniqueEmail();

    await page.goto("/inscription");
    await page.getByLabel(/e-mail/i).fill(email);
    await page.getByLabel(/mot de passe/i).fill(PASSWORD);
    await page.getByLabel(/j'accepte les conditions/i).check();
    await page.getByRole("button", { name: /créer mon espace/i }).click();
    await expect(page.getByText(/vérifie ta boîte mail/i)).toBeVisible();

    const emailBody = await waitForEmail(email);
    const token = extractTokenFromEmail(emailBody);
    await page.goto(`/verifier?token=${token}`);
    await page.getByRole("link", { name: /se connecter/i }).click();
    await page.getByLabel(/e-mail/i).fill(email);
    await page.getByLabel(/mot de passe/i).fill(PASSWORD);
    await page.getByRole("button", { name: /se connecter/i }).click();
    await page.waitForURL("/");

    const uploadId = seedValidationUpload(email);

    await page.goto(`/ajouter/validation?uploads=${uploadId}`);
    await expect(page.getByText(/1 carte trouvée/i)).toBeVisible();
    await expect(page.getByText(/Sarmuraï/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /valider/i })).toBeVisible();

    await page.screenshot({
      path: "../../docs/roadmap/comptes-rendus/assets/v3-validation-ecran.png",
      fullPage: true,
    });

    await page.getByRole("button", { name: /valider/i }).click();
    await expect(page.getByText("validée")).toBeVisible();
    await expect(page.getByRole("button", { name: /valider/i })).not.toBeVisible();
  });
});
