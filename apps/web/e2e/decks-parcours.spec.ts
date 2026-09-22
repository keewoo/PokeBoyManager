import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

/**
 * Parcours complet du gestionnaire de decks (lot `v7-decks-e2e`, mission §3).
 *
 * Le module a beaucoup de chemins — création manuelle, recherche au catalogue, quantités,
 * légalité recalculée côté serveur, duplication, export, et synchronisation avec la collection
 * (`v7-decks-collection-sync`). Chaque lot a livré son test ciblé ; ce fichier joue le PARCOURS
 * de bout en bout, celui qu'un joueur suit vraiment, pour attraper les régressions d'enchaînement
 * qu'aucun test isolé ne voit — plus la vérification des largeurs sur les écrans du module et
 * l'isolation par utilisateur de la route d'export (nouvelle en e2e).
 *
 * Comme `deck-builder.spec.ts` : l'utilisateur et sa collection sont semés directement en base
 * (`apps/api/scripts/seed_deck_builder_e2e.py`, quatre Ronflex possédés + une Énergie de base
 * fournie), jamais via `POST /auth/register` (limité en débit par IP, compteur partagé par toutes
 * les specs e2e). La connexion passe par `POST /auth/login`, dont le scope de débit est distinct.
 *
 * L'assistant IA de construction (`v7-deck-ia`) n'est PAS rejoué ici : il exige une vraie clé du
 * joueur, absente de la CI. Un essai réel est fait à la main et consigné dans le compte rendu du
 * lot (mission §4).
 */

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";
const DECK_URL = /\/jeu\/decks\/[0-9a-f-]{36}$/;

const WIDTHS = [320, 390, 768, 1280];
const HEIGHT = 900;

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

/** Le jeton CSRF est déposé en cookie lisible ; le client web le renvoie en en-tête sur les
 * écritures. On fait pareil pour reproduire fidèlement une suppression de collection. */
async function csrfToken(page: Page): Promise<string> {
  const cookies = await page.context().cookies();
  return cookies.find((c) => c.name.toLowerCase().includes("csrf"))?.value ?? "";
}

async function assertNoHorizontalScroll(page: Page, label: string): Promise<void> {
  const { scrollWidth, innerWidth, offenders } = await page.evaluate(() => {
    const iw = window.innerWidth;
    const out: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("*"))) {
      const r = el.getBoundingClientRect();
      if (r.right > iw + 1 || r.left < -1) {
        const cls = typeof el.className === "string" ? el.className.split(/\s+/).slice(0, 4).join(".") : "";
        out.push(`${el.tagName.toLowerCase()}.${cls} left=${Math.round(r.left)} right=${Math.round(r.right)} w=${Math.round(r.width)}`);
      }
    }
    return { scrollWidth: document.documentElement.scrollWidth, innerWidth: iw, offenders: out.slice(0, 15) };
  });
  expect(
    scrollWidth,
    `${label} : défilement horizontal (scrollWidth=${scrollWidth} > innerWidth=${innerWidth})\nÉléments qui débordent :\n${offenders.join("\n")}`
  ).toBeLessThanOrEqual(innerWidth);
}

test.describe("Parcours complet du gestionnaire de decks (lot v7-decks-e2e)", () => {
  test("créer, remplir à 60, exporter, dupliquer, subir l'alerte de synchro, corriger", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const email = uniqueEmail("e2e-parcours");
    seedUser(email);
    await login(page, email);

    // 1. Créer le deck depuis « Mes decks » → on arrive sur le constructeur.
    await page.goto("/jeu/decks");
    await page.getByLabel("Nom du deck").fill("Parcours E2E");
    await page.getByRole("button", { name: /Créer et construire/i }).click();
    await page.waitForURL(DECK_URL);

    // 2. Chercher et ajouter des cartes jusqu'à 60 : 4 Ronflex possédés + 56 Énergie de base
    //    fournie. La légalité, recalculée côté serveur à chaque écriture, bascule sur « Légal ✓ ».
    await page.getByLabel("Chercher une carte au catalogue").fill("Ronflex");
    await page.getByRole("button", { name: "Ajouter Ronflex E2E au deck" }).click();
    await page.getByLabel("Quantité de Ronflex E2E").fill("4");
    await page.getByLabel("Chercher une carte au catalogue").fill("Énergie");
    await page.getByRole("button", { name: "Ajouter Énergie E2E au deck" }).click();
    await page.getByLabel("Quantité de Énergie E2E").fill("56");
    await expect(page.getByText(/Deck · 60 \/ 60/)).toBeVisible();
    await expect(page.getByText("Légal ✓")).toBeVisible();

    // 3. Exporter (texte) : le bouton déclenche un vrai téléchargement (fetch → blob → ancre).
    //    On capte le `download` et on lit le fichier — le nom porte le deck, le corps ses cartes.
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Exporter (texte)" }).click(),
    ]);
    // Le NOM du fichier dépend de l'exposition CORS de `Content-Disposition` : en e2e, l'API
    // (:8100) et le web (:3100) sont d'origines distinctes et cet en-tête n'est pas exposé au
    // navigateur, donc le client retombe sur son nom par défaut « deck.txt » (en PROD, même
    // origine → le vrai nom « <deck>.txt »). On vérifie donc l'extension, puis le CONTENU — qui,
    // lui, ne dépend pas de l'origine — pour prouver que c'est bien CE deck qui a été exporté.
    expect(download.suggestedFilename()).toMatch(/\.txt$/);
    const downloadPath = await download.path();
    const exported = fs.readFileSync(downloadPath, "utf-8");
    expect(exported).toContain("# Parcours E2E");
    expect(exported).toContain("Ronflex E2E");
    expect(exported).toContain("Énergie E2E");

    // 4. Dupliquer depuis la liste : un second deck « … (copie) » apparaît, légal lui aussi.
    await page.goto("/jeu/decks");
    await expect(page.getByRole("link", { name: "Parcours E2E", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Dupliquer" }).first().click();
    await expect(page.getByRole("link", { name: "Parcours E2E (copie)" })).toBeVisible();
    await expect(page.getByText("Légal", { exact: true })).toHaveCount(2);

    // 5. Vendre un Ronflex = supprimer un exemplaire de la collection, exactement comme la page
    //    Collection (DELETE + jeton CSRF). Les deux decks reposaient sur 4 Ronflex possédés.
    const csrf = await csrfToken(page);
    const list = await page.request.get(`${API_BASE_URL}/me/collection`);
    const items = (await list.json()).items as Array<{ id: string; card_name: string }>;
    const ronflex = items.find((i) => i.card_name.includes("Ronflex"));
    expect(ronflex).toBeTruthy();
    const del = await page.request.delete(`${API_BASE_URL}/me/collection/${ronflex!.id}`, {
      headers: { "X-CSRF-Token": csrf },
    });
    expect(del.ok()).toBeTruthy();

    // 6. La liste des decks annonce l'alerte et les DEUX decks passent « À compléter » — sans
    //    qu'aucune carte n'ait été retirée d'un deck (mission `v7-decks-collection-sync`).
    await page.goto("/jeu/decks");
    await expect(page.getByTestId("deck-alerts-notice")).toBeVisible();
    await expect(page.getByText("À compléter", { exact: true })).toHaveCount(2);

    // 7. Corriger le deck original : ramener Ronflex à 3 (le nombre désormais possédé) et porter
    //    l'Énergie à 57 (jamais décomptée) → 60/60, de nouveau « Légal ✓ ».
    await page.getByRole("link", { name: "Parcours E2E", exact: true }).click();
    await page.waitForURL(DECK_URL);
    await expect(page.getByText("Illégal")).toBeVisible();
    await page.getByLabel("Quantité de Ronflex E2E").fill("3");
    await page.getByLabel("Quantité de Énergie E2E").fill("57");
    await expect(page.getByText(/Deck · 60 \/ 60/)).toBeVisible();
    await expect(page.getByText("Légal ✓")).toBeVisible();
  });

  test("aucun défilement horizontal sur les écrans du module à 320/390/768/1280px", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const email = uniqueEmail("e2e-decks-resp");
    seedUser(email);
    await login(page, email);

    // Un deck garni pour mesurer le constructeur avec de vrais contenus (recherche + liste).
    await page.goto("/jeu/decks");
    await page.getByLabel("Nom du deck").fill("Deck responsive");
    await page.getByRole("button", { name: /Créer et construire/i }).click();
    await page.waitForURL(DECK_URL);
    const deckPath = new URL(page.url()).pathname;
    await page.getByLabel("Chercher une carte au catalogue").fill("Ronflex");
    await page.getByRole("button", { name: "Ajouter Ronflex E2E au deck" }).click();
    await page.getByLabel("Quantité de Ronflex E2E").fill("4");
    await expect(page.getByText(/Deck · 4 \/ 60/)).toBeVisible();

    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: HEIGHT });
      for (const p of ["/jeu/decks", deckPath]) {
        await page.goto(p);
        await page.waitForLoadState("networkidle");
        await assertNoHorizontalScroll(page, `${p} @ ${width}px`);
      }
    }
  });

  test("l'export d'un deck est borné au propriétaire (accès croisé, 404 jamais 403)", async ({
    page,
    browser,
  }) => {
    test.setTimeout(90_000);
    const ownerEmail = uniqueEmail("e2e-exp-owner");
    const otherEmail = uniqueEmail("e2e-exp-other");
    seedUser(ownerEmail);
    seedUser(otherEmail);

    // A crée un deck et note son identifiant.
    await login(page, ownerEmail);
    await page.goto("/jeu/decks");
    await page.getByLabel("Nom du deck").fill("Deck exportable de A");
    await page.getByRole("button", { name: /Créer et construire/i }).click();
    await page.waitForURL(DECK_URL);
    const deckId = page.url().match(/([0-9a-f-]{36})$/)![1];

    // A exporte le sien : 200.
    const own = await page.request.get(`${API_BASE_URL}/me/decks/${deckId}/export?fmt=text`);
    expect(own.status()).toBe(200);

    // B, dans un autre contexte, tente d'exporter le deck de A : 404 (pas 403 : aucune fuite
    // d'existence), jamais le contenu du deck de A.
    const contextB = await browser.newContext();
    const pageB = await contextB.newPage();
    await login(pageB, otherEmail);
    const resB = await pageB.request.get(`${API_BASE_URL}/me/decks/${deckId}/export?fmt=text`);
    expect(resB.status()).toBe(404);
    await contextB.close();
  });
});
