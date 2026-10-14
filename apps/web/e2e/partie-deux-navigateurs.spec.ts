// Lot `j-e2e-deux-navigateurs` — une partie entière jouée automatiquement, à deux navigateurs.
//
// C'est la seule preuve qui vaut pour le jeu : deux contextes Playwright (deux joueurs, deux
// sessions), une partie menée de la connexion à l'écran de fin, sans la moindre intervention —
// puis les quatre parcours dégradés, là où sont les vraies pannes.
//
// **Comment le pilote décide.** Le serveur fait autorité : le test ne rejoue aucune règle et ne
// devine jamais ce qui est jouable. À chaque coup il lit `GET /games/{id}/state`, dont
// `actions_legales` porte — pour le joueur qui appelle — le `type`, l'`etiquette` exacte du
// bouton, ses `cibles` et son drapeau `irreversible`. Le test clique ensuite CE bouton dans
// l'interface, illumine une cible si le serveur en annonce, confirme si le serveur dit que le coup
// est irréversible. L'écran est donc réellement traversé (c'est un e2e, pas un appel d'API), mais
// rien n'est codé en dur côté test : si le moteur change l'étiquette d'un coup, le test suit.
//
// **Pourquoi la partie finit vite et légitimement.** `scripts/seed_partie_e2e.py` donne au joueur A
// un attaquant à 60 dégâts et au joueur B un unique Pokémon à 110 PV sans attaque : deux attaques
// mettent B K.O., et comme son banc est vide **par construction** il n'a plus personne à promouvoir
// — deuxième voie de victoire de **R-14.1**, adossée à **R-8.9**. Une vraie fin de partie, pas un
// abandon. Mesuré : 32 coups.
//
// Lire aussi `docs/jeu/E2E-PARTIE.md` (ce que chaque parcours prouve, et les pièges).

import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect, type Browser, type Page, type TestInfo } from "@playwright/test";
import { API_BASE_URL } from "../playwright.config";

const PASSWORD = "un-mot-de-passe-tres-solide";
const API_DIR = path.resolve(process.cwd(), "../api");
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ||
  "postgresql+asyncpg://pbm:pbm@localhost:55432/pbm_v1_pages_auth_e2e";

/** Garde-fou de boucle : très au-dessus des 32 coups mesurés, mais borné (jamais de boucle folle). */
const COUPS_MAX = 120;

/**
 * Nombre de refus tolérés sur une partie. Un refus légitime existe — le conflit de numéro à la
 * mise en place, où les deux joueurs peuvent placer au même numéro (voir `jouerUnCoup`) — mais il
 * est rare. Au-delà, les coups ne passent plus et le test échoue en citant tous les motifs.
 */
const REFUS_MAX = 8;

/**
 * Ordre de priorité des coups du joueur **A** (l'attaquant). `attacher_energie` d'abord — sans
 * énergie, pas d'attaque — puis les Dresseurs (pour que le parcours en traverse), puis l'attaque,
 * et enfin le passage de phase quand il n'y a plus rien à faire.
 */
const ORDRE_A = [
  "placer_mise_en_place",
  "promouvoir",
  "attacher_energie",
  "jouer_supporter",
  "jouer_objet",
  "declarer_attaque",
  "avancer_phase",
] as const;

/**
 * Ordre de priorité du joueur **B** (la cible) : il place, promeut si on le lui demande, et passe.
 * Il ne pose **jamais** au banc — son deck ne contient qu'un Pokémon, donc il ne peut pas, mais on
 * l'écrit tout de même : c'est cette absence de banc qui rend la fin de partie atteignable.
 */
const ORDRE_B = ["placer_mise_en_place", "promouvoir", "avancer_phase"] as const;

/**
 * Plafond de Dresseurs joués sur toute la partie, par genre.
 *
 * Il ne s'agit pas d'une règle du jeu mais d'une **borne du pilote**. L'Objet du deck A pioche une
 * carte : s'il est rejoué dès qu'il réapparaît en main, A brûle son deck et finit par perdre par
 * pioche impossible (**R-14.2**) — mesuré, 123 coups et la victoire à B, l'inverse de ce que le
 * parcours doit prouver. Deux de chaque suffisent à prouver qu'un Dresseur se joue.
 */
const BUDGET_DRESSEURS = { jouer_objet: 2, jouer_supporter: 2 };

type Semence = { user_a: string; user_b: string; deck_a: string; deck_b: string };
/** Un coup tenté : son type, et la raison affichée par l'écran s'il a été refusé. */
type Coup = { type: string; refuse: string | null };
type Cible = { genre: string; reference: string; etiquette: string };
type ActionLegale = {
  type: string;
  params: Record<string, unknown>;
  etiquette: string;
  cibles: Cible[];
  irreversible: boolean;
};
/**
 * La réponse de `GET /games/{id}/state`. Attention à la forme : la projection est **imbriquée**
 * sous `vue` (c'est `vue_autoritaire` qui pose `actions_legales` dans `sortie["vue"]`), tandis que
 * `numero` et `horloges` sont ajoutés à la **racine** par la route. `partie-view.tsx` lit exactement
 * cela (`etat.vue`, `etat.numero`) : chercher `actions_legales` à la racine rend une liste vide, et
 * le pilote croirait que personne n'a de coup à jouer.
 */
type EtatPartie = {
  numero: number;
  vue?: { actions_legales?: ActionLegale[]; [k: string]: unknown };
  [k: string]: unknown;
};

function uniqueEmail(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.fr`;
}

/** Lance un script de seed de l'API et rend sa sortie standard (il échoue fort, jamais en silence). */
function seed(script: string, ...args: string[]): string {
  return execFileSync("uv", ["run", "python", `scripts/${script}`, ...args], {
    cwd: API_DIR,
    env: { ...process.env, DATABASE_URL },
    encoding: "utf-8",
  });
}

/** Sème deux comptes « accès jeu » et leurs deux decks jouables, et rend leurs identifiants. */
function semerPartie(emailA: string, emailB: string): Semence {
  return JSON.parse(seed("seed_partie_e2e.py", emailA, emailB, PASSWORD)) as Semence;
}

/** Connexion par l'API (le formulaire est couvert par `auth.spec.ts`, et `/auth/register` est
 *  limité en débit par IP : le compte est semé, pas inscrit). Le cookie atterrit dans le contexte. */
async function connecter(page: Page, email: string) {
  const res = await page.request.post(`${API_BASE_URL}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  expect(res.ok(), `connexion de ${email}`).toBeTruthy();
}

/** La vue autoritaire du serveur pour le joueur de cette page. */
async function lireEtat(page: Page, gameId: string): Promise<EtatPartie> {
  const res = await page.request.get(`${API_BASE_URL}/games/${gameId}/state`);
  expect(res.ok(), `GET /games/${gameId}/state`).toBeTruthy();
  return (await res.json()) as EtatPartie;
}

/** Les coups que le serveur déclare jouables pour le joueur de cette page. */
function legalesDe(etat: EtatPartie): ActionLegale[] {
  return etat.vue?.actions_legales ?? [];
}

/**
 * Attend que le serveur ait dépassé `minimum`, et rend `false` s'il ne l'a pas fait à temps.
 *
 * Rend un booléen au lieu d'échouer : l'appelant doit pouvoir distinguer « coup refusé, avec la
 * raison à l'écran » de « rien ne se passe », et dire lequel des deux. Un `expect.poll` échouerait
 * ici sans jamais lire le motif du refus.
 */
async function attendreNumero(
  page: Page,
  gameId: string,
  minimum: number,
  timeoutMs: number,
): Promise<boolean> {
  const fin = Date.now() + timeoutMs;
  while (Date.now() < fin) {
    if ((await lireEtat(page, gameId)).numero > minimum) return true;
    await page.waitForTimeout(250);
  }
  return false;
}

/** Joint une capture au rapport Playwright — c'est elle qu'on publie depuis la CI. */
async function capturer(page: Page, info: TestInfo, nom: string) {
  await info.attach(nom, { body: await page.screenshot(), contentType: "image/png" });
}

/**
 * Fait entrer un joueur dans la file **par l'écran**, en vérifiant au passage que son deck est
 * déclaré jouable (D9) : c'est `salon-jouabilite` qui conditionne le bouton, et un deck refusé
 * laisserait « Entrer dans la file » désactivé — panne silencieuse si on ne l'affirmait pas.
 */
async function entrerDansLaFile(page: Page, deckId: string) {
  await page.goto("/jeu/salon");
  await page.getByTestId("salon-deck-select").selectOption(deckId);
  await expect(page.getByTestId("salon-jouabilite")).toContainText("Deck jouable");
  const bouton = page.getByRole("button", { name: /Entrer dans la file/ });
  await expect(bouton).toBeEnabled();
  await bouton.click();
}

/**
 * Apparie les deux joueurs par la file d'attente et rend l'identifiant de la partie.
 *
 * Le salon ne redirige pas tout seul : il re-interroge `GET /matchmaking/queue` toutes les 4 s et
 * affiche « Adversaire trouvé ! » avec un lien. On traverse donc ce que vit un joueur — attente,
 * appariement, clic — plutôt que de sauter à l'URL de la partie.
 */
async function apparier(pageA: Page, pageB: Page, s: Semence): Promise<string> {
  await entrerDansLaFile(pageA, s.deck_a);
  await expect(pageA.getByTestId("salon-attente")).toBeVisible();
  await entrerDansLaFile(pageB, s.deck_b);

  for (const page of [pageA, pageB]) {
    await expect(page.getByTestId("salon-apparie")).toBeVisible({ timeout: 20_000 });
  }
  await pageA.getByRole("link", { name: /Rejoindre la partie/ }).click();
  await expect(pageA.getByTestId("plateau")).toBeVisible({ timeout: 20_000 });
  const gameId = new URL(pageA.url()).pathname.split("/").pop();
  expect(gameId, "identifiant de partie dans l'URL").toBeTruthy();

  await pageB.getByRole("link", { name: /Rejoindre la partie/ }).click();
  await expect(pageB.getByTestId("plateau")).toBeVisible({ timeout: 20_000 });
  expect(new URL(pageB.url()).pathname, "les deux joueurs sur la même partie").toContain(gameId!);
  return gameId!;
}

/**
 * Joue **un** coup pour ce joueur s'il en a un, en passant par l'interface. Rend le type du coup
 * joué, ou `null` si le serveur ne lui en propose aucun (ce n'est pas son tour).
 *
 * `abandonner` est toujours légal : il n'est dans aucun ordre de priorité, donc une main qui ne
 * contient que lui rend bien `null` — sans quoi le pilote abandonnerait la partie au premier tour.
 */
async function jouerUnCoup(
  page: Page,
  gameId: string,
  camp: "A" | "B",
  budgets: Record<string, number>,
): Promise<Coup | null> {
  const etat = await lireEtat(page, gameId);
  const legales = legalesDe(etat);
  const ordre = camp === "A" ? ORDRE_A : ORDRE_B;

  let choix: ActionLegale | undefined;
  for (const type of ordre) {
    const reste = budgets[type];
    if (reste !== undefined && reste <= 0) continue; // budget de ce genre de coup épuisé
    choix = legales.find((l) => l.type === type);
    if (choix) break;
  }
  if (!choix) return null;
  const retenu = choix; // fige le type pour la suite (TypeScript perd la narrowing sur un `let`)

  // Le bouton porte l'étiquette que le moteur a produite : on le désigne par elle, pas par un
  // libellé recopié ici (plusieurs coups partagent un même `data-testid`).
  const bouton = page.getByRole("button", { name: retenu.etiquette, exact: true }).first();
  // Attente généreuse : le plateau verrouille toute la barre d'actions pendant qu'un coup est en
  // vol (anti double-envoi). Or on détecte l'enregistrement d'un coup en interrogeant `/state`,
  // qui voit la transaction commitée **avant** que la réponse du POST ne soit revenue au
  // navigateur — on arrive donc régulièrement un instant trop tôt, écran encore verrouillé.
  await expect(bouton, `bouton « ${retenu.etiquette} » (${camp})`).toBeEnabled({
    timeout: 30_000,
  });
  await bouton.click();

  if (retenu.cibles.length > 0) {
    // Coup ciblé : l'écran passe en ciblage et illumine les cibles valides.
    await expect(page.getByTestId("ciblage")).toBeVisible();
    await page.locator("[data-illumine]").first().click();
  }
  if (retenu.irreversible) {
    // Coup irréversible (R-5.7 / R-14.3) : l'écran demande un « oui » explicite.
    await expect(page.getByTestId("confirmation")).toBeVisible();
    await page.getByTestId("confirmer").click();
  }

  // Le coup n'est joué que quand le serveur l'a journalisé : on attend que le numéro avance.
  if (await attendreNumero(page, gameId, etat.numero, 15_000)) {
    const reste = budgets[retenu.type];
    if (reste !== undefined) budgets[retenu.type] = reste - 1;
    return { type: retenu.type, refuse: null };
  }

  // Pas d'avancée. Si l'écran affiche une raison, le coup a été REFUSÉ — ce n'est pas un blocage,
  // et c'est même le comportement attendu dans un cas précis : à la mise en place, les DEUX
  // joueurs ont « placer » légal au même numéro de coup (R-4). Le premier à soumettre prend le
  // numéro ; l'autre reçoit un conflit (409) et l'écran lui montre la raison du serveur. Un joueur
  // humain re-clique, et ça passe — c'est exactement ce que fait l'appelant.
  const refus = page.getByTestId("refus-coup");
  if ((await refus.count()) > 0) {
    return { type: retenu.type, refuse: ((await refus.textContent()) ?? "").trim() };
  }
  throw new Error(
    `le coup ${retenu.type} (${camp}) n'a pas été enregistré et l'écran n'affiche aucune raison ` +
      `(numéro resté à ${etat.numero}) — ni joué, ni refusé : c'est une panne.`,
  );
}

/**
 * Fait avancer la partie jusqu'à ce que `fini()` soit vrai, en alternant les deux navigateurs.
 *
 * À chaque passage on tente A puis B : celui dont c'est le tour a des coups, l'autre rend `null`.
 * Deux passages de suite sans aucun coup des deux côtés = la partie est bloquée, et c'est une
 * **panne** : on échoue en le disant, on ne sort pas de la boucle en silence.
 */
async function jouer(
  pageA: Page,
  pageB: Page,
  gameId: string,
  fini: () => Promise<boolean>,
  budgets: Record<string, number> = { ...BUDGET_DRESSEURS },
): Promise<string[]> {
  const joues: string[] = [];
  const refus: string[] = [];
  let steriles = 0;
  for (let i = 0; i < COUPS_MAX; i++) {
    if (await fini()) return joues;
    const coup =
      (await jouerUnCoup(pageA, gameId, "A", budgets)) ??
      (await jouerUnCoup(pageB, gameId, "B", budgets));

    if (coup === null) {
      steriles += 1;
      expect(
        steriles,
        `partie bloquée : aucun coup proposé aux deux joueurs (coups joués : ${joues.join(", ")})`,
      ).toBeLessThan(3);
      await pageA.waitForTimeout(1_000);
      continue;
    }
    steriles = 0;

    if (coup.refuse !== null) {
      // Un refus est une information, pas une panne — mais il reste borné et nommé : s'ils
      // s'accumulent, c'est que les coups ne passent plus et le test doit le dire avec les motifs.
      refus.push(`${coup.type} : ${coup.refuse}`);
      expect(
        refus.length,
        `trop de coups refusés d'affilée — motifs :\n${refus.join("\n")}`,
      ).toBeLessThan(REFUS_MAX);
      continue;
    }
    joues.push(coup.type);
  }
  throw new Error(`la partie n'est pas finie après ${COUPS_MAX} coups : ${joues.join(", ")}`);
}

/** Vrai dès que le serveur déclare la partie terminée (c'est lui qui fait autorité, pas l'écran). */
function partieTerminee(page: Page, gameId: string) {
  return async () => {
    const res = await page.request.get(`${API_BASE_URL}/games/${gameId}`);
    expect(res.ok()).toBeTruthy();
    return ((await res.json()) as { status: string }).status !== "en_cours";
  };
}

/** Ouvre les deux navigateurs, sème, connecte, apparie — le préambule commun à tous les parcours. */
async function deuxJoueurs(browser: Browser, prefixe: string) {
  const emailA = uniqueEmail(`${prefixe}-a`);
  const emailB = uniqueEmail(`${prefixe}-b`);
  const s = semerPartie(emailA, emailB);

  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();
  await connecter(pageA, emailA);
  await connecter(pageB, emailB);
  const gameId = await apparier(pageA, pageB, s);

  return {
    s,
    pageA,
    pageB,
    gameId,
    fermer: async () => {
      await ctxA.close();
      await ctxB.close();
    },
  };
}

/** Mène la mise en place (R-4) : les deux joueurs posent leur Actif, le premier tour peut commencer. */
async function miseEnPlace(pageA: Page, pageB: Page, gameId: string) {
  await jouer(pageA, pageB, gameId, async () => {
    // La condition porte sur les DEUX joueurs. N'interroger que A s'arrêtait dès qu'A avait placé,
    // en laissant B sans Actif : la partie restait en mise en place, et les parcours qui comptaient
    // sur un tour commencé (expiration d'horloge, abandon) mesuraient autre chose que ce qu'ils
    // annonçaient — l'expiration, elle, ne se produisait tout simplement pas.
    const [a, b] = await Promise.all([lireEtat(pageA, gameId), lireEtat(pageB, gameId)]);
    return ![...legalesDe(a), ...legalesDe(b)].some((x) => x.type === "placer_mise_en_place");
  });
}

test.describe("Partie complète à deux navigateurs", () => {
  test("parcours nominal : de la file d'attente à l'historique du compte", async ({
    browser,
  }, info) => {
    test.setTimeout(300_000);
    const { s, pageA, pageB, gameId, fermer } = await deuxJoueurs(browser, "nominal");
    try {
      await capturer(pageA, info, "01-plateau-ouverture-joueur-A");

      const joues = await jouer(pageA, pageB, gameId, partieTerminee(pageA, gameId));

      // Le parcours a bien traversé ce que le lot exige : mise en place, attaques, Dresseurs.
      expect(joues, "mise en place jouée").toContain("placer_mise_en_place");
      expect(
        joues.filter((c) => c === "declarer_attaque").length,
        "au moins deux attaques (le K.O. en demande deux)",
      ).toBeGreaterThanOrEqual(2);
      expect(
        joues.some((c) => c === "jouer_objet" || c === "jouer_supporter"),
        `au moins un Dresseur joué (coups : ${joues.join(", ")})`,
      ).toBeTruthy();

      // Fin de partie : A gagne parce que B n'a plus de Pokémon à promouvoir (R-14.1, R-8.9).
      const detail = await (await pageA.request.get(`${API_BASE_URL}/games/${gameId}`)).json();
      expect(detail.status).toBe("terminee");
      expect(detail.vainqueur_user_id, "le joueur A gagne").toBe(s.user_a);
      expect(detail.raison_fin, "la fin est un vrai K.O., pas un abandon").toBe("plus_de_pokemon");

      await expect(pageA.getByTestId("fin-partie")).toBeVisible({ timeout: 30_000 });
      await expect(pageA.getByTestId("fin-partie-titre")).toContainText("Gagné");
      await expect(pageB.getByTestId("fin-partie")).toBeVisible({ timeout: 30_000 });
      await capturer(pageA, info, "02-fin-de-partie-gagnant");
      await capturer(pageB, info, "03-fin-de-partie-perdant");

      // ⛔ Critère d'acceptation du lot : le test ÉCHOUE si l'historique du compte n'est pas à
      // jour. On le lit là où le joueur le lit — le salon — et des deux côtés : un historique
      // écrit pour le seul gagnant serait un demi-bug qu'une assertion unique laisserait passer.
      await pageA.goto("/jeu/salon");
      await expect(pageA.getByTestId("salon-dernier-resultat")).toContainText("Victoire");
      await pageB.goto("/jeu/salon");
      await expect(pageB.getByTestId("salon-dernier-resultat")).toContainText("Défaite");
      await capturer(pageA, info, "04-historique-du-compte-gagnant");

      // Et la partie figure bien dans la liste du compte, terminée, avec son vainqueur.
      const liste = await (await pageA.request.get(`${API_BASE_URL}/games`)).json();
      const ligne = (liste as { id: string; status: string; vainqueur_user_id: string }[]).find(
        (g) => g.id === gameId,
      );
      expect(ligne, "la partie apparaît dans l'historique du compte").toBeTruthy();
      expect(ligne!.status).toBe("terminee");
      expect(ligne!.vainqueur_user_id).toBe(s.user_a);
    } finally {
      await fermer();
    }
  });

  test("dégradé — F5 au milieu : le plateau se redessine et la partie continue", async ({
    browser,
  }, info) => {
    test.setTimeout(240_000);
    const { pageA, pageB, gameId, fermer } = await deuxJoueurs(browser, "f5");
    try {
      await miseEnPlace(pageA, pageB, gameId);
      // Quelques coups pour avoir un état à perdre, puis on recharge les DEUX navigateurs.
      await jouer(pageA, pageB, gameId, async () => (await lireEtat(pageA, gameId)).numero >= 6);
      const avant = await lireEtat(pageA, gameId);

      await pageA.reload();
      await pageB.reload();
      for (const page of [pageA, pageB]) {
        await expect(page.getByTestId("plateau")).toBeVisible({ timeout: 30_000 });
      }
      await capturer(pageA, info, "05-apres-F5");

      // Rien n'a été perdu : le serveur rejoue le journal, l'écran retrouve le même état.
      const apres = await lireEtat(pageA, gameId);
      expect(apres.numero, "le numéro de coup survit au rechargement").toBe(avant.numero);
      await expect(pageA.getByTestId("main-joueur")).toBeVisible();

      // Et surtout : la partie se joue encore. Un plateau qui se redessine mais n'accepte plus de
      // coup serait une panne que la seule vérification d'affichage laisserait passer.
      const joues = await jouer(
        pageA,
        pageB,
        gameId,
        async () => (await lireEtat(pageA, gameId)).numero >= apres.numero + 2,
      );
      expect(joues.length, "des coups sont encore acceptés après le F5").toBeGreaterThan(0);
    } finally {
      await fermer();
    }
  });

  test("dégradé — abandon : les deux écrans l'annoncent, l'historique le retient", async ({
    browser,
  }, info) => {
    test.setTimeout(240_000);
    const { s, pageA, pageB, gameId, fermer } = await deuxJoueurs(browser, "abandon");
    try {
      await miseEnPlace(pageA, pageB, gameId);

      // L'abandon est un coup légal comme un autre (R-14.3), irréversible : il se confirme.
      await pageA.getByTestId("action-abandonner").click();
      await expect(pageA.getByTestId("confirmation")).toBeVisible();
      await pageA.getByTestId("confirmer").click();

      await expect(pageA.getByTestId("fin-partie")).toBeVisible({ timeout: 30_000 });
      await expect(pageB.getByTestId("fin-partie")).toBeVisible({ timeout: 30_000 });
      await expect(pageA.getByTestId("fin-partie-raison-courte")).toContainText("abandon");
      await capturer(pageA, info, "06-abandon-celui-qui-abandonne");
      await capturer(pageB, info, "07-abandon-l-adversaire");

      const detail = await (await pageB.request.get(`${API_BASE_URL}/games/${gameId}`)).json();
      expect(detail.status).toBe("terminee");
      expect(detail.raison_fin).toBe("abandon");
      expect(detail.vainqueur_user_id, "celui qui abandonne perd (R-14.3)").toBe(s.user_b);

      await pageA.goto("/jeu/salon");
      await expect(pageA.getByTestId("salon-dernier-resultat")).toContainText("Défaite");
      await pageB.goto("/jeu/salon");
      await expect(pageB.getByTestId("salon-dernier-resultat")).toContainText("Victoire");
    } finally {
      await fermer();
    }
  });

  test("dégradé — expiration d'horloge : défaite au temps, sans que personne ne clique", async ({
    browser,
  }, info) => {
    test.setTimeout(240_000);
    const { pageA, pageB, gameId, fermer } = await deuxJoueurs(browser, "horloge");
    try {
      await miseEnPlace(pageA, pageB, gameId);

      // On épuise le budget du joueur dont le compteur tourne. Personne ne déclenche l'expiration
      // ici : le seul déclencheur en production est le battement de cœur du WebSocket, toutes les
      // 20 s de silence (`pbm_api.games.temps_reel.piloter_canal`). Les deux navigateurs restent
      // donc ouverts, et on attend — c'est exactement le scénario réel d'un joueur qui part.
      const { joueur } = JSON.parse(seed("forcer_horloge_e2e.py", gameId)) as { joueur: string };
      expect(joueur, "un joueur a bien un compteur en cours").toBeTruthy();

      await expect(pageA.getByTestId("fin-partie")).toBeVisible({ timeout: 90_000 });
      await expect(pageB.getByTestId("fin-partie")).toBeVisible({ timeout: 90_000 });
      await capturer(pageA, info, "08-expiration-horloge");

      const detail = await (await pageA.request.get(`${API_BASE_URL}/games/${gameId}`)).json();
      expect(detail.status).toBe("terminee");
      expect(detail.raison_fin, "la fin est bien une défaite au temps (DJ4)").toBe("temps_ecoule");
      expect(detail.vainqueur_user_id, "celui dont le temps est écoulé perd").not.toBe(joueur);
    } finally {
      await fermer();
    }
  });

  test("dégradé — déconnexion puis reprise : repli en interrogation périodique", async ({
    browser,
  }, info) => {
    test.setTimeout(240_000);
    const emailA = uniqueEmail("sondage-a");
    const emailB = uniqueEmail("sondage-b");
    const s = semerPartie(emailA, emailB);

    const ctxA = await browser.newContext();
    const ctxB = await browser.newContext();
    const pageA = await ctxA.newPage();
    const pageB = await ctxB.newPage();
    try {
      await connecter(pageA, emailA);
      await connecter(pageB, emailB);

      // On coupe le temps réel du joueur A avant qu'il n'arrive sur le plateau : le canal compte
      // ses échecs et, au troisième, replie sur `GET /games/{id}/sync` toutes les 2 s.
      let wsCoupe = true;
      await pageA.routeWebSocket(/\/ws/, (ws) => {
        if (wsCoupe) ws.close();
      });

      const gameId = await apparier(pageA, pageB, s);
      const degrade = pageA.locator('[data-etat="degrade"]');
      await expect(degrade, "le joueur voit que sa connexion est dégradée").toBeVisible({
        timeout: 30_000,
      });
      await expect(degrade).toContainText("la partie continue");
      await capturer(pageA, info, "09-connexion-degradee");

      // La partie doit se jouer **quand même** : c'est tout l'intérêt du repli. On la mène
      // jusqu'au bout, A étant en interrogation périodique du début à la fin.
      const joues = await jouer(pageA, pageB, gameId, partieTerminee(pageA, gameId));
      expect(
        joues.filter((c) => c === "declarer_attaque").length,
        "la partie s'est jouée entièrement en mode dégradé",
      ).toBeGreaterThanOrEqual(2);

      const detail = await (await pageA.request.get(`${API_BASE_URL}/games/${gameId}`)).json();
      expect(detail.status).toBe("terminee");
      expect(detail.vainqueur_user_id).toBe(s.user_a);
      await expect(pageA.getByTestId("fin-partie")).toBeVisible({ timeout: 30_000 });
      await capturer(pageA, info, "10-fin-de-partie-en-mode-degrade");

      // Reprise : le temps réel rétabli, le bandeau de dégradation disparaît après un rechargement
      // — la reconnexion ne laisse pas l'écran menteur.
      wsCoupe = false;
      await pageA.reload();
      await expect(pageA.getByTestId("plateau")).toBeVisible({ timeout: 30_000 });
      await expect(degrade, "la connexion rétablie, plus de bandeau").toBeHidden({
        timeout: 30_000,
      });
      await capturer(pageA, info, "11-connexion-retablie");
    } finally {
      await ctxA.close();
      await ctxB.close();
    }
  });
});
