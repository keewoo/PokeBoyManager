import { execFileSync } from "node:child_process";
import path from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";

import { API_BASE_URL } from "../playwright.config";

// Lot `j-accessibilite-jeu` — **l'audit d'accessibilité des écrans de jeu**, second niveau.
//
// Le premier niveau (`src/__tests__/a11y-jeu.test.tsx`, en jsdom) couvre la structure : rôles,
// étiquettes, `aria-*` invalides. Il ne peut pas couvrir ce qui exige une peinture réelle, et c'est
// précisément ce que ce fichier mesure :
//
// - le **contraste** (WCAG 1.4.3) : `axe` a besoin des couleurs effectives, donc d'un navigateur ;
// - la **taille des cibles** : on mesure les boîtes réelles des contrôles du plateau, et l'échec
//   NOMME le coupable (sélecteur + dimensions) — un test qui dirait seulement « trop petit »
//   obligerait à tout rouvrir à la main ;
// - la **navigation au clavier** : Tab atteint les coups, Entrée les joue, Échap ferme les
//   surcouches ;
// - le **texte agrandi sur le plateau** : le plateau ne tolère aucun défilement (lot
//   `j-plateau-layout`), et un réglage d'accessibilité qui le casserait serait un piège. On le
//   vérifie au lieu de l'espérer.
//
// La vue de partie est **simulée** par interception réseau, exactement comme
// `plateau-responsive.spec.ts` : ce qu'on audite est l'ÉCRAN, pas le moteur (couvert par
// `partie-deux-navigateurs.spec.ts`). C'est ce qui permet d'auditer un plateau complet en deux
// secondes au lieu d'une partie entière à deux navigateurs.

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

/** Le minimum WCAG 2.2 pour une cible de pointage (2.5.8, niveau AA), en pixels CSS. */
const CIBLE_MIN = 24;

const PAYSAGE = { width: 844, height: 390 };

function uniqueEmail(): string {
  return `e2e-a11y-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Accorde le droit d'accès au jeu (D11) à un compte dédié, sans passer par l'inscription (débit). */
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

/**
 * Pose des réglages de confort **côté serveur**, par l'API.
 *
 * Et pas dans `localStorage` : le fournisseur relit le serveur dès qu'une session existe et écrase
 * le cache local — c'est voulu (les réglages suivent le compte, pas l'appareil). Un test qui ne
 * poserait que le cache mesurerait donc l'inverse de ce qu'il croit. Constaté en écrivant ce
 * fichier.
 */
async function reglerConfort(page: Page, patch: Record<string, unknown>): Promise<void> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((c) => c.name.toLowerCase().includes("csrf"))?.value ?? "";
  const res = await page.request.patch(`${API_BASE_URL}/jeu/confort/reglages`, {
    data: patch,
    headers: { "X-CSRF-Token": csrf },
  });
  expect(res.ok(), `PATCH /jeu/confort/reglages : ${res.status()}`).toBeTruthy();
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

/**
 * La vue projetée d'une partie **jouable** : elle porte `actions_legales` et `actions_refusees`,
 * sans quoi la barre d'actions serait vide et l'audit du clavier ne prouverait rien.
 */
function vueSimulee() {
  const banc = (prefixe: string) => [0, 1].map((n) => pokemon(`${prefixe}-banc${n}`));
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
        main: [0, 1, 2].map((n) => ({ instance_id: `h${n}`, ref: `main-${n}` })),
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
    actions_legales: [
      {
        type: "attacher_energie",
        params: {},
        etiquette: "Attacher Énergie Eau",
        cibles: [],
        irreversible: false,
      },
      { type: "avancer_phase", params: {}, etiquette: "Finir mon tour", cibles: [], irreversible: true },
    ],
    actions_refusees: [
      {
        type: "retraite",
        etiquette: "Retraite",
        message: "la retraite a déjà été faite ce tour-ci",
        regle: "R-7.3",
      },
    ],
  };
}

/** Intercepte les routes de partie pour servir la vue simulée, sans moteur ni partie réelle. */
async function stubPartie(page: Page): Promise<void> {
  const vue = vueSimulee();
  await page.route("**/games/*/state", (route) => route.fulfill({ json: { vue, evenements: [] } }));
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

/**
 * Lance `axe` sur la page et échoue en **nommant** chaque manquement avec son sélecteur.
 *
 * On retient les niveaux **A et AA** de WCAG 2.2 : c'est le socle écrit dans `docs/UI-UX.md`, et
 * AAA imposerait des cibles de 44 px que l'arène d'un plateau sans défilement ne peut pas tenir
 * (voir `docs/jeu/ACCESSIBILITE.md`).
 */
async function auditer(
  page: Page,
  ecran: string,
  options: { sansTailleDeCible?: boolean } = {},
): Promise<void> {
  let constructeur = new AxeBuilder({ page }).withTags([
    "wcag2a",
    "wcag2aa",
    "wcag21a",
    "wcag21aa",
    "wcag22aa",
  ]);
  if (options.sansTailleDeCible) {
    // `target-size` (2.5.8) est désactivée **sur le plateau seulement**, et c'est un choix motivé,
    // pas un contournement. Mesuré : une carte de banc fait 4,7 × 6,5 px sur un téléphone en
    // paysage, parce que l'arène met neuf zones par joueur à l'échelle d'un écran qui ne doit pas
    // défiler (lot `j-plateau-layout`). L'agrandir casserait le plateau.
    // 2.5.8 prévoit exactement ce cas par son exception « Equivalent » : la fonction est atteignable
    // par un AUTRE contrôle de la même page qui, lui, respecte le minimum — tout coup jouable sur
    // une carte est un bouton de la barre d'actions, et `assertCibles` vérifie ces boutons-là.
    // S'y ajoutent le clavier (Tab + Entrée) et l'agrandissement au focus (`CardZoom`).
    // Détail et mesures : `docs/jeu/ACCESSIBILITE.md`.
    constructeur = constructeur.disableRules(["target-size"]);
  }
  const resultat = await constructeur.analyze();
  const detail = resultat.violations
    .map(
      (v) =>
        `  • ${v.id} (${v.impact}) — ${v.help}\n    ` +
        v.nodes.map((n) => n.target.join(" ")).join("\n    "),
    )
    .join("\n");
  expect(resultat.violations, `${ecran} : ${resultat.violations.length} manquement(s)\n${detail}`)
    .toEqual([]);
}

/** Mesure les cibles d'un ensemble de contrôles et nomme celles qui sont sous le minimum. */
async function assertCibles(page: Page, selecteur: string, label: string): Promise<void> {
  const trop_petites = await page.evaluate(
    ({ selecteur, min }) =>
      Array.from(document.querySelectorAll<HTMLElement>(selecteur))
        .filter((el) => el.offsetParent !== null)
        .map((el) => {
          const r = el.getBoundingClientRect();
          return {
            quoi: el.getAttribute("data-testid") ?? el.textContent?.trim().slice(0, 30) ?? "?",
            w: Math.round(r.width),
            h: Math.round(r.height),
          };
        })
        // Tolérance d'un pixel : une bordure fractionnaire ne doit pas faire échouer un contrôle
        // dimensionné pile au minimum.
        .filter((m) => m.w < min - 1 || m.h < min - 1),
    { selecteur, min: CIBLE_MIN },
  );
  expect(
    trop_petites,
    `${label} : cible(s) sous ${CIBLE_MIN}×${CIBLE_MIN} px — ` +
      trop_petites.map((m) => `${m.quoi} (${m.w}×${m.h})`).join(", "),
  ).toEqual([]);
}

test.describe("Audit d'accessibilité : les écrans de jeu", () => {
  test("salon, decks, confort et « mes cartes en jeu » passent l'audit", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);

    // Le repère attendu doit exister pour un compte NEUF : `seed_game_access_e2e.py` donne l'accès
    // au jeu, pas un deck — `salon-deck-select` n'apparaît donc pas, et l'attendre faisait échouer
    // l'audit avant même de l'avoir lancé.
    for (const [chemin, repere] of [
      ["/jeu/salon", "salon-lien-confort"],
      ["/jeu/confort", "confort-temps-rallonge"],
      ["/jeu/rendu", "jamais-montrer"],
      // Lot `j-profil-jeu` : le repère est la page elle-même, rendue pour un compte NEUF (sans
      // carte fétiche, badges éteints) — un repère qui dépendrait d'un badge obtenu ferait échouer
      // l'audit avant de l'avoir lancé, le piège exact décrit plus haut.
      ["/jeu/profil", "profil-jeu"],
    ] as const) {
      await page.goto(chemin);
      await expect(page.getByTestId(repere)).toBeVisible();
      await auditer(page, chemin);
    }

    // Les decks : un compte neuf n'en a aucun, donc aucun contenu de liste n'est garanti — on
    // attend le titre de la section, qui est rendu dans tous les cas.
    await page.goto("/jeu/decks");
    await expect(page.getByRole("heading", { name: "Mes decks" })).toBeVisible();
    await auditer(page, "/jeu/decks");
  });

  test("le plateau d'une partie jouable passe l'audit, contraste compris", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();
    await expect(page.getByTestId("barre-actions")).toBeVisible();

    await auditer(page, "plateau @ 844×390", { sansTailleDeCible: true });
  });

  test("les contrôles du plateau atteignent la taille de cible minimale", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Les boutons de la barre d'actions, du journal et de l'aide. On exclut les cartes du plateau :
    // elles sont dimensionnées par l'arène (une carte de banc fait moins de 24 px de large sur un
    // téléphone en paysage) et sont atteignables autrement — au clavier, et par le zoom.
    await assertCibles(page, '[data-testid="barre-actions"] button', "barre d'actions");
    await assertCibles(page, '[data-testid="journal"] button', "journal");
  });

  test("une partie se joue au clavier seul : Tab atteint les coups, Entrée les joue", async ({
    page,
  }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);
    // Le coup part réellement : on intercepte l'envoi pour le constater sans moteur derrière.
    let coupEnvoye: string | null = null;
    await page.route("**/games/*/actions", async (route) => {
      coupEnvoye = route.request().postData();
      await route.fulfill({ status: 409, json: { detail: "numéro périmé (vue simulée)" } });
    });

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // On part du haut du document et on tabule jusqu'au premier coup jouable. Borné : si le
    // plateau n'est pas atteignable au clavier, le test échoue en le disant, il ne boucle pas.
    const coup = page.getByTestId("action-attacher_energie");
    await expect(coup).toBeVisible();
    let atteint = false;
    for (let i = 0; i < 60 && !atteint; i += 1) {
      await page.keyboard.press("Tab");
      atteint = await coup.evaluate((el) => el === document.activeElement);
    }
    expect(atteint, "le premier coup jouable n'est pas atteignable au Tab en 60 tabulations").toBe(
      true,
    );

    await page.keyboard.press("Enter");
    await expect
      .poll(() => coupEnvoye, { message: "aucun coup envoyé après Entrée" })
      .not.toBeNull();
    expect(coupEnvoye).toContain("attacher_energie");
  });

  test("Échap ferme la carte agrandie ouverte au clavier", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();

    // Le zoom s'ouvre au focus d'une carte : c'est donc par le clavier qu'on y entre, et c'était
    // un cul-de-sac avant ce lot (aucune touche ne le fermait).
    await page.getByRole("button", { name: /Mon actif/ }).focus();
    await expect(page.getByTestId("card-zoom")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("card-zoom")).toBeHidden();
  });

  test("texte agrandi : les écrans grossissent, le plateau ne défile pas", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);

    await reglerConfort(page, { taille_texte: "tres_grande" });

    // 1) Hors partie, le réglage AGIT : la police de la racine grossit, donc tout ce qui est en
    //    `rem` avec elle. Sans cette moitié du test, la seconde serait satisfaite par un réglage
    //    qui ne fait rien du tout.
    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/confort");
    await expect(page.getByTestId("confort-temps-rallonge")).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-texte")), {
        message: "le réglage de taille n'a pas été appliqué au document",
      })
      .toBe("tres_grande");
    const grossie = await page.evaluate(
      () => parseFloat(getComputedStyle(document.documentElement).fontSize),
    );
    expect(grossie, "la police de la racine n'a pas grossi hors partie").toBeGreaterThan(16);

    // 2) Sur le plateau, le MÊME réglage est volontairement neutralisé (`data-ecran="plateau"`) :
    //    mesuré, il portait le document à 432 px pour 390 disponibles — un plateau qui défile,
    //    c'est-à-dire une régression du critère d'acceptation de `j-plateau-layout`. La lisibilité
    //    en partie passe par l'agrandissement d'une carte. Voir `docs/jeu/ACCESSIBILITE.md`.
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.getAttribute("data-ecran"))).toBe(
      "plateau",
    );
    const surPlateau = await page.evaluate(
      () => parseFloat(getComputedStyle(document.documentElement).fontSize),
    );
    expect(surPlateau, "la police du plateau doit rester celle du navigateur").toBe(16);

    const { scrollHeight, innerHeight, scrollWidth, innerWidth } = await page.evaluate(() => ({
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight: window.innerHeight,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
    }));
    expect(
      scrollHeight,
      `texte très grand : défilement vertical (${scrollHeight} > ${innerHeight})`,
    ).toBeLessThanOrEqual(innerHeight + 4);
    expect(
      scrollWidth,
      `texte très grand : défilement horizontal (${scrollWidth} > ${innerWidth})`,
    ).toBeLessThanOrEqual(innerWidth);
  });

  test("animations réduites : aucune animation n'est rendue sur le plateau", async ({ page }) => {
    const email = uniqueEmail();
    seedGameAccess(email);
    await login(page, email);
    await stubPartie(page);
    await reglerConfort(page, { animations: "reduites" });

    await page.setViewportSize(PAYSAGE);
    await page.goto("/jeu/parties/simulee");
    await expect(page.getByTestId("plateau")).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.getAttribute("data-anim")), {
        message: "le réglage d'animation n'a pas été appliqué au document",
      })
      .toBe("reduites");
    // L'état du plateau reste lisible : c'est la seconde moitié du critère d'acceptation (« sans
    // changer la lisibilité de l'état »).
    await expect(page.getByText("mon-actif")).toBeVisible();
    await expect(page.getByTestId("anim-couche")).toHaveCount(0);
  });
});
