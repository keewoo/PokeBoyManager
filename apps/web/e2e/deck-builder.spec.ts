import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

/**
 * Constructeur de deck (lot `v7-decks-ui`, mission §3.3 et §6) : construire un deck LÉGAL à
 * partir de sa collection, puis vérifier l'isolation par utilisateur (le deck de A renvoie
 * « introuvable » à B).
 *
 * L'utilisateur et sa collection sont semés directement en base
 * (`apps/api/scripts/seed_deck_builder_e2e.py`) — quatre exemplaires d'un Pokémon de base légal
 * Standard —, jamais via `POST /auth/register` (limité en débit par IP, compteur partagé par
 * toutes les specs e2e, cf. `parcours-complet.spec.ts`). La connexion passe par `POST
 * /auth/login`, dont le scope de débit est distinct.
 *
 * Un deck de 4 × ce Pokémon + 56 × une Énergie de base (fournie, jamais décomptée) = 60 cartes
 * possédées en Standard : la légalité, recalculée côté serveur à chaque écriture, bascule sur
 * « Légal ✓ » sans qu'aucune règle ne soit dupliquée côté écran.
 */

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";
const DECK_URL = /\/jeu\/decks\/[0-9a-f-]{36}$/;

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

function seedUser(email: string): void {
  execFileSync("uv", ["run", "python", "scripts/seed_deck_builder_e2e.py", email, PASSWORD], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

async function login(page: Page, email: string): Promise<void> {
  await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
}

test.describe("Constructeur de deck (lot v7-decks-ui)", () => {
  test("construire un deck légal à partir de sa collection", async ({ page }) => {
    test.setTimeout(90_000);
    const email = uniqueEmail("e2e-deck");
    seedUser(email);
    await login(page, email);

    // 1. Créer le deck depuis « Mes decks » → on arrive sur le constructeur.
    await page.goto("/jeu/decks");
    await page.getByLabel("Nom du deck").fill("Deck E2E légal");
    await page.getByRole("button", { name: /Créer et construire/i }).click();
    await page.waitForURL(DECK_URL);

    // 2. Ajouter le Pokémon de base possédé, puis porter sa quantité à 4.
    await page.getByLabel("Chercher une carte au catalogue").fill("Ronflex");
    await page
      .getByRole("button", { name: "Ajouter Ronflex E2E au deck" })
      .click();
    const pokemonQty = page.getByLabel("Quantité de Ronflex E2E");
    await expect(pokemonQty).toBeVisible();
    await pokemonQty.fill("4");

    // 3. Ajouter l'Énergie de base et la porter à 56 exemplaires (56 + 4 = 60).
    await page.getByLabel("Chercher une carte au catalogue").fill("Énergie");
    await page.getByRole("button", { name: "Ajouter Énergie E2E au deck" }).click();
    const energyQty = page.getByLabel("Quantité de Énergie E2E");
    await expect(energyQty).toBeVisible();
    await energyQty.fill("56");

    // 4. La légalité, recalculée côté serveur, bascule sur « Légal ✓ » à 60/60.
    await expect(page.getByText(/Deck · 60 \/ 60/)).toBeVisible();
    await expect(page.getByText("Légal ✓")).toBeVisible();

    // 5. « Retirer un exemplaire » ramène sous les 60 et rend le deck illégal (mission §3.2).
    await page.getByRole("button", { name: "Retirer un exemplaire de Énergie E2E" }).click();
    await expect(page.getByText(/Deck · 59 \/ 60/)).toBeVisible();
    await expect(page.getByText("Illégal")).toBeVisible();
  });

  test("un deck n'est visible que par son propriétaire (accès croisé)", async ({
    page,
    browser,
  }) => {
    test.setTimeout(60_000);
    const ownerEmail = uniqueEmail("e2e-deck-owner");
    const otherEmail = uniqueEmail("e2e-deck-other");
    seedUser(ownerEmail);
    seedUser(otherEmail);

    // A crée un deck et retient son URL.
    await login(page, ownerEmail);
    await page.goto("/jeu/decks");
    await page.getByLabel("Nom du deck").fill("Deck privé de A");
    await page.getByRole("button", { name: /Créer et construire/i }).click();
    await page.waitForURL(DECK_URL);
    const deckUrl = page.url();

    // B, dans un autre contexte, visite l'URL de A : « introuvable » (404, jamais 403 : pas de
    // fuite d'existence), et jamais le nom du deck de A.
    const contextB = await browser.newContext();
    const pageB = await contextB.newPage();
    await login(pageB, otherEmail);
    await pageB.goto(deckUrl);
    await expect(pageB.getByText("Deck introuvable")).toBeVisible();
    await expect(pageB.getByText("Deck privé de A")).toHaveCount(0);
    await contextB.close();
  });
});
