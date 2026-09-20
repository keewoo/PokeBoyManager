import { execFileSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { test, expect } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";
import { extractTokenFromEmail, waitForEmail } from "./mailpit";

/**
 * Parcours e2e complet (lot `v5-e2e`, mission §3) : inscription → vérification (Mailpit) → clé
 * IA (simulée) → envoi de la photo de référence 3×3 → validation → collection filtrée → fiche
 * carte.
 *
 * Contrairement à `validation.spec.ts`/`card-detail.spec.ts` (résultat de reconnaissance semé
 * directement en base, aucune clé IA réelle sur chimera), ce lot fait tourner le *vrai* pipeline
 * de bout en bout : un vrai fichier envoyé par le navigateur, une vraie détection OpenCV, une
 * vraie identification + rapprochement catalogue — seul l'aller-retour réseau vers le
 * fournisseur IA est remplacé par `SimulatedProvider` (drapeau `AI_SIMULATED_PROVIDER`, jamais
 * activé hors e2e, voir `playwright.config.ts` et `pbm_api.ai.simulated_provider`). Ça exige un
 * worker arq réel (troisième entrée `webServer` de `playwright.config.ts` — jusqu'ici aucune
 * spec n'en avait besoin).
 *
 * Les neuf recadrages du classeur synthétique sont visuellement indiscernables (pensés pour la
 * géométrie de détection, pas l'identification, voir `pbm_api.detection.synthetic`) : le cache
 * d'identification (une vraie fonctionnalité de production) résout donc les neuf détections sur
 * la même carte de démonstration après un seul appel simulé — les neuf exemplaires confirmés sont
 * neuf « Sarmuraï » (doublons), pas neuf cartes distinctes. Le filtre de collection est quand même
 * exercé dans les deux sens (une recherche qui trouve, une qui ne trouve rien).
 *
 * Volontairement hors périmètre : les onglets Histoire/En jeu de la fiche carte, qui
 * appelleraient un vrai wiki + la clé IA (fournisseur simulé non branché sur ces schémas, voir
 * `pbm_api.ai.simulated_provider`) — non exercés ici, déjà couverts sans réseau par
 * `card-detail.spec.ts` (résultat seedé). Voir le compte rendu pour le détail des écarts.
 */

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

function runApiScript(...args: string[]): string {
  return execFileSync("uv", ["run", "python", ...args], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  }).trim();
}

/** Second utilisateur du test d'accès croisé, créé directement en base
 * (`scripts/seed_e2e_second_user.py`) plutôt que via `POST /auth/register` : cette route est
 * limitée en débit par IP depuis le lot `v5-securite` (`register:ip`, 5 tentatives/15 min,
 * partagées par toutes les specs e2e de ce fichier Playwright) — le parcours principal en
 * consomme déjà une en s'inscrivant à l'écran, une seconde inscription par ce même job dépasserait
 * le total déjà consommé par `auth.spec.ts`/`validation.spec.ts`/`card-detail.spec.ts`. `POST
 * /auth/login`, utilisé ici, a son propre scope de débit (`login:ip`), sans lien avec celui-ci. */
async function loginAsSeededUser(
  request: import("@playwright/test").APIRequestContext,
  email: string
): Promise<void> {
  runApiScript("scripts/seed_e2e_second_user.py", email, PASSWORD);
  await request.post(`${API_BASE_URL}/auth/login`, { data: { email, password: PASSWORD } });
}

test.describe("Parcours complet (lot v5-e2e)", () => {
  test.beforeAll(() => {
    // Idempotent (voir le script) : les neuf cartes de démonstration + un historique de prix
    // minimal, nécessaires au rapprochement catalogue et à la valeur affichée en collection/fiche.
    runApiScript("scripts/seed_e2e_reference_catalog.py");
  });

  test("inscription → vérification → clé IA → envoi 3×3 → validation → collection → fiche", async ({
    page,
    browser,
  }) => {
    test.setTimeout(120_000); // vrai pipeline (détection + 9 identifications + worker arq)
    const email = uniqueEmail("e2e-parcours");

    // 1. Inscription
    await page.goto("/inscription");
    await page.getByLabel(/^nom$/i).fill("Dresseur");
    await page.getByLabel(/date de naissance/i).fill("2000-01-01");
    await page.getByLabel(/e-mail/i).fill(email);
    await page.getByLabel(/mot de passe/i).fill(PASSWORD);
    await page.getByLabel(/j'accepte les conditions/i).check();
    await page.getByRole("button", { name: /créer mon espace/i }).click();
    await expect(page.getByText(/vérifie ta boîte mail/i)).toBeVisible();

    // 2. Vérification (Mailpit) puis connexion
    const emailBody = await waitForEmail(email);
    const token = extractTokenFromEmail(emailBody);
    await page.goto(`/verifier?token=${token}`);
    await page.getByRole("link", { name: /se connecter/i }).click();
    await page.getByLabel(/e-mail/i).fill(email);
    await page.getByLabel(/mot de passe/i).fill(PASSWORD);
    await page.getByRole("button", { name: /se connecter/i }).click();
    await page.waitForURL("/");

    // 3. Clé IA (simulée) : `PUT /me/ai-keys` ne fait que chiffrer et stocker la valeur (aucun
    // appel réseau) — jamais testée contre le vrai fournisseur ici (bouton « Tester », qui
    // appellerait réellement Anthropic, volontairement non cliqué : voir le compte rendu).
    await page.goto("/profil");
    await page.getByRole("button", { name: "Mon IA" }).click();
    // Les trois fournisseurs (Anthropic/Gemini/OpenAI) affichent chacun un bouton
    // « Enregistrer » tant qu'aucune clé n'est configurée ; Anthropic est le premier de la liste
    // (`PROVIDERS`, `ai-tab.tsx`) — son champ, lui, est déjà univoque (libellé distinct par
    // fournisseur).
    await page.getByLabel(/Clé API Claude/i).fill("sk-ant-e2e-simulee-0000000000000000");
    await page.getByRole("button", { name: "Enregistrer" }).first().click();
    await expect(page.getByText("enregistrée")).toBeVisible();

    // 4. Envoi de la photo de référence 3×3 (classeur propre, sans reflets — OpenCV seul détecte
    // les neuf cartes, aucun repli LLM exercé par ce test).
    const photoPath = path.join(mkdtempSync(path.join(tmpdir(), "pbm-e2e-")), "classeur-3x3.jpg");
    runApiScript("scripts/generate_e2e_reference_photo.py", photoPath);

    await page.goto("/ajouter");
    await page.setInputFiles('input[aria-label="Choisir des fichiers"]', photoPath);
    await page.getByRole("button", { name: /lancer la reconnaissance/i }).click();
    await page.waitForURL(/\/ajouter\/validation\?uploads=/);
    const uploadId = new URL(page.url()).searchParams.get("uploads");
    expect(uploadId).toBeTruthy();

    // 5. Validation — le vrai pipeline tourne (worker arq + fournisseur simulé, voir l'en-tête du
    // fichier) : les neuf cartes de démonstration doivent être identifiées avec confiance et
    // présélectionnées (rapprochement catalogue exact numéro + extension).
    await expect(page.getByText(/9 cartes trouvées/i)).toBeVisible({ timeout: 60_000 });
    const confirmAllButton = page.getByRole("button", { name: /Ajouter les \d+ cartes? validées/ });
    await expect(confirmAllButton).toHaveText(/Ajouter les 9 cartes/, { timeout: 60_000 });
    await confirmAllButton.click();
    await page.waitForURL("/collection");

    // 6. Collection filtrée — les neuf recadrages du classeur synthétique sont visuellement
    // indiscernables (mêmes couleurs/formes, `pbm_api.detection.synthetic.draw_card`, pensé pour
    // la géométrie, pas l'identification) : leur empreinte perceptuelle est donc identique et le
    // cache d'identification (`identification_cache`, une vraie fonctionnalité de production)
    // résout les neuf détections sur la même carte de démonstration après le premier appel
    // simulé — les neuf exemplaires confirmés sont donc neuf « Sarmuraï » (doublons), pas neuf
    // cartes distinctes. Une diversité réelle demanderait des photos distinctes, indisponibles
    // sur chimera (même contrainte que `v3-detection`, voir le compte rendu). Le filtre est
    // exercé dans les deux sens : une recherche qui trouve, une qui ne trouve rien.
    await expect(page.getByText(/9 cartes/i).first()).toBeVisible();
    await page.getByLabel(/Chercher dans ma collection/i).fill("Sarmuraï");
    await expect(page.getByRole("link", { name: /Sarmuraï/ }).first()).toBeVisible();
    await page.getByLabel(/Chercher dans ma collection/i).fill("Mewtwo");
    await expect(page.getByText("Aucune carte ne correspond à ces filtres.")).toBeVisible();
    await page.getByLabel(/Chercher dans ma collection/i).fill("Sarmuraï");

    // 7. Fiche carte
    await page.getByRole("link", { name: /Sarmuraï/ }).first().click();
    await page.waitForURL(/\/carte\//);
    await expect(page.getByRole("heading", { name: "Sarmuraï" })).toBeVisible();
    await page.getByRole("tab", { name: "Mes exemplaires" }).click();
    await expect(page.getByRole("table")).toBeVisible();

    // Test d'accès croisé : un second utilisateur ne voit rien de l'envoi/des détections
    // produits par le vrai pipeline ci-dessus (contrairement à `validation.spec.ts`/
    // `card-detail.spec.ts`, dont le résultat est semé directement en base — l'isolation sur un
    // envoi/détections réels n'était encore exercée nulle part).
    const otherContext = await browser.newContext();
    try {
      const otherRequest = otherContext.request;
      await loginAsSeededUser(otherRequest, uniqueEmail("e2e-parcours-autre"));

      const uploadResponse = await otherRequest.get(`${API_BASE_URL}/uploads/${uploadId}`);
      expect(uploadResponse.status()).toBe(404);

      const detectionsResponse = await otherRequest.get(
        `${API_BASE_URL}/uploads/${uploadId}/detections`
      );
      expect(detectionsResponse.status()).toBe(404);
    } finally {
      await otherContext.close();
    }
  });
});
