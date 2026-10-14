import { execFileSync } from "node:child_process";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

// Lot `j-rendu-carte`, critère : « les trois rendus sont lisibles à la taille du plateau sur
// téléphone ». C'est un critère de **géométrie**, pas de goût : on mesure la boîte réellement
// rendue, dans un vrai navigateur, sur le téléphone d'un enfant tenu en paysage.
//
// Deux choses sont vérifiées, et la seconde est celle qui a déjà cassé ce dépôt (cf.
// `plateau-responsive.spec.ts`) : ajouter une image sur chaque carte ne doit introduire **aucun
// défilement** sur `/jeu/parties/{id}`.
//
// La vue de partie est **simulée** par interception réseau, exactement comme
// `plateau-responsive.spec.ts` : ce test porte sur le RENDU, pas sur le moteur. Les images le sont
// aussi — un PNG au format d'une carte (63×88), servi pour l'URL de photo comme pour celle de
// l'image officielle : le navigateur fait le même travail de mise en page qu'avec de vraies images,
// sans dépendre du catalogue ni du réseau.

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

const PAYSAGE = { width: 844, height: 390 };
const PORTRAIT = { width: 390, height: 844 };

/** Un PNG 63×88 (le format d'une carte) : de quoi mesurer une mise en page réelle. */
const CARTE_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAD8AAABYCAIAAADNzLhqAAAAYUlEQVR42u3OQQkAAAgEsIthBNPZ/2kAEwiDBVi65q/" +
    "Y29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vb29vbHwtga7kD" +
    "ePFv2wAAAABJRU5ErkJggg==",
  "base64",
);

function uniqueEmail(): string {
  return `e2e-rendu-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Accorde le droit d'accès au jeu (D11) à un compte dédié, sans passer par l'inscription. */
function seedGameAccess(email: string): void {
  execFileSync("uv", ["run", "python", "scripts/seed_game_access_e2e.py", email, PASSWORD], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

/** Le rendu « ma photo », tel que le serveur le pose sur une carte (DJ5). */
function renduPhoto(credit: string | null) {
  return {
    origine: "photo",
    url: "/jeu/rendu/parties/simulee/photos/item-1",
    url_zoom: "/jeu/rendu/parties/simulee/photos/item-1",
    credit,
    url_repli: "/img/cards/c-1?size=low",
  };
}

/** Le rendu « image officielle ». */
function renduOfficielle() {
  return {
    origine: "officielle",
    url: "/img/cards/c-2?size=low",
    url_zoom: "/img/cards/c-2?size=high",
    credit: null,
    raison: "aucune photo de cette carte",
  };
}

function pokemon(ref: string, rendu: object) {
  return {
    cartes: [{ instance_id: `i-${ref}`, ref, rendu }],
    // Une énergie attachée et un Stade posé (comme `plateau-responsive.spec.ts`) : la taille des
    // cartes dépend de la place que prend l'arène, on mesure donc un plateau garni, pas un plateau
    // vide qui donnerait des chiffres plus flatteurs que la réalité.
    energies: [{ instance_id: `e-${ref}`, ref: "energie", rendu }],
    outil: null,
    compteurs_degats: 0,
    etats_speciaux: [],
    orientation: "normale",
  };
}

/** La vue projetée d'une partie où **les deux rendus** sont présents en même temps. */
function vueSimulee(options: { demandeCachee?: boolean } = {}) {
  const banc = (prefixe: string, rendu: object) =>
    [0, 1, 2].map((n) => pokemon(`${prefixe}-banc${n}`, rendu));
  const vue: Record<string, unknown> = {
    schema_version: 1,
    pour: "a",
    joueurs: [
      {
        id: "a",
        actif: pokemon("mon-actif", renduPhoto(null)),
        banc: banc("moi", renduPhoto(null)),
        defausse: [],
        zone_perdue: [],
        pioche_nombre: 41,
        recompenses_nombre: 6,
        main: [0, 1, 2, 3, 4].map((n) => ({
          instance_id: `h${n}`,
          ref: `main-${n}`,
          rendu: renduPhoto(null),
        })),
        recompenses_jetons: ["j1", "j2", "j3", "j4", "j5", "j6"],
      },
      {
        id: "b",
        // L'adversaire montre SES photos : la carte porte le crédit de son propriétaire.
        actif: pokemon("actif-adverse", renduPhoto("photo de Aymeric")),
        banc: banc("adv", renduOfficielle()),
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
    stade: { instance_id: "s1", ref: "stade-partage", rendu: renduOfficielle() },
    stade_proprietaire: "a",
    terminee: false,
    vainqueur: null,
    raison_fin: null,
  };
  if (options.demandeCachee) {
    // Un ensemble **caché** : le serveur n'en donne que le nombre. L'écran montre donc des DOS de
    // carte — le troisième rendu — sans qu'aucune identité ne circule.
    vue.demande = {
      id: "d-1",
      destinataire: "a",
      categorie: "cartes",
      libelle: "Choisis une carte dans la main de ton adversaire",
      regle: "R-9.1",
      obligatoire: true,
      minimum: 1,
      maximum: 1,
      source: { libelle: "Fouille" },
      delai_ms: null,
      temps_restant_ms: null,
      options_nombre: 6,
    };
  }
  return vue;
}

async function login(page: Page, email: string): Promise<void> {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), "connexion du compte de test").toBeTruthy();
}

async function stubPartie(page: Page, options: { demandeCachee?: boolean } = {}): Promise<void> {
  const vue = vueSimulee(options);
  // Les deux familles d'URL d'image servent le même PNG : ce qui est mesuré est la mise en page,
  // pas le contenu. Rien ne sort vers le catalogue ni vers l'API de photos.
  await page.route("**/img/cards/**", (route) =>
    route.fulfill({ body: CARTE_PNG, contentType: "image/png" }),
  );
  await page.route("**/jeu/rendu/parties/**", (route) =>
    route.fulfill({ body: CARTE_PNG, contentType: "image/png" }),
  );
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

test.describe("Rendu des cartes : lisible à la taille du plateau, sans allonger la page", () => {
  test("les images couvrent la carte et la page ne défile pas (844×390 puis 390×844)", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    const monActif = page.getByRole("button", { name: /Mon actif/ });
    await expect(monActif).toBeVisible();
    const image = monActif.getByTestId("image-carte");
    await expect(image).toBeVisible();

    // L'image **remplit** la carte : si elle était plus petite, la carte serait illisible alors que
    // la place existe ; si elle était plus grande, elle déborderait sur les voisines.
    const boiteCarte = await monActif.boundingBox();
    const boiteImage = await image.boundingBox();
    expect(boiteCarte, "la carte doit avoir une boîte mesurable").not.toBeNull();
    expect(boiteImage, "l'image doit avoir une boîte mesurable").not.toBeNull();
    expect(Math.abs(boiteImage!.width - boiteCarte!.width)).toBeLessThanOrEqual(2);
    expect(Math.abs(boiteImage!.height - boiteCarte!.height)).toBeLessThanOrEqual(2);
    // La boîte n'est pas dégénérée. On n'exige PAS plus : sur un téléphone tenu en paysage, la
    // carte du plateau est délibérément minuscule (quelques pixels de large — mesuré à 11 px en
    // CI), et c'est assumé par le plateau : « minuscule sur un téléphone en paysage, d'où le
    // zoom » (`board-card.tsx`). La lisibilité se prouve donc sur le ZOOM, pas sur la vignette —
    // c'est l'objet du test « le zoom agrandit l'image assez pour la lire ».
    expect(
      boiteCarte!.width,
      `carte de ${Math.round(boiteCarte!.width)} px de large en paysage : boîte dégénérée`,
    ).toBeGreaterThan(4);

    await assertNoScroll(page, "plateau avec images @ 844×390 paysage");

    await page.setViewportSize(PORTRAIT);
    await expect(page.getByTestId("plateau")).toBeVisible();
    await assertNoScroll(page, "plateau avec images @ 390×844 portrait");
  });

  test("les deux rendus coexistent : ma photo d'un côté, l'officielle de l'autre", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Mon actif : ma photo. Le banc adverse : l'image officielle. Le serveur a décidé des deux,
    // l'écran n'a rien choisi — et les deux s'affichent côte à côte sans se gêner.
    await expect(
      page.getByRole("button", { name: /Mon actif/ }).locator('[data-origine="photo"]'),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /banc adverse 1/ }).locator('[data-origine="officielle"]'),
    ).toBeVisible();

    // Le crédit de la photo de l'adversaire est annoncé sur sa carte (il est écrit dans le zoom).
    await expect(page.getByRole("button", { name: /photo de Aymeric/ })).toBeVisible();

    await assertNoScroll(page, "deux rendus côte à côte @ 844×390");
  });

  test("le zoom agrandit l'image assez pour la lire sans pincer l'écran", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Le zoom s'ouvre au **focus clavier** (`onFocus`, câblé comme le survol) : c'est le chemin
    // qu'on veut garantir, et il ne dépend pas du pointage — une carte de plateau large de 11 px
    // en paysage n'est pas une cible de survol fiable.
    await page.getByRole("button", { name: /Mon actif/ }).focus();
    const zoom = page.getByTestId("card-zoom");
    await expect(zoom).toBeVisible();
    const imageZoom = zoom.getByTestId("image-carte");
    await expect(imageZoom).toBeVisible();
    const boite = await imageZoom.boundingBox();
    expect(boite, "l'image zoomée doit avoir une boîte mesurable").not.toBeNull();
    expect(
      boite!.width,
      `image zoomée de ${Math.round(boite!.width)} px : on devrait encore pincer l'écran`,
    ).toBeGreaterThanOrEqual(150);

    await assertNoScroll(page, "zoom ouvert @ 844×390");
  });

  test("un ensemble caché montre des DOS de carte, sans révéler aucune identité", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page, { demandeCachee: true });

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");

    const cache = page.getByTestId("decision-ensemble-cache");
    await expect(cache).toBeVisible();
    // Le troisième rendu : des dos de carte, dessinés (aucune image chargée), en nombre.
    await expect(cache.getByTestId("dos-carte").first()).toBeVisible();
    expect(await cache.getByTestId("dos-carte").count()).toBe(6);
    await assertNoScroll(page, "fenêtre d'ensemble caché @ 844×390");
  });
});
