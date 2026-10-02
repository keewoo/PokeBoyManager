// Canal temps réel d'une partie, côté navigateur (lot `j-temps-reel`).
//
// Le serveur fait autorité : ce module ne décide de rien. Il ouvre un WebSocket, applique les coups
// **par numéro de séquence** (jamais par ordre d'arrivée — c'est ce qui le rend insensible au
// désordre et aux doublons), détecte un trou et redemande une resynchronisation, et **replie en
// interrogation périodique** (`GET /games/{id}/sync`) quand le WebSocket est impossible (réseau
// d'école, proxy). L'état de connexion est remonté à l'écran, qui annonce « connexion dégradée ».
//
// La logique est isolée du navigateur par des points d'injection (`creerWebSocket`, `fetchSync`,
// `maintenant`) : elle se teste intégralement en mémoire, sans vrai socket ni vrai réseau.

import { getApiBaseUrl } from "@/lib/config";

/** État de la connexion temps réel, tel qu'affiché au joueur. */
export type EtatConnexion = "connexion" | "direct" | "degrade" | "ferme";

/** Un coup diffusé : son numéro de séquence et ses événements déjà projetés par le serveur. */
export type Coup = { numero: number; evenements: unknown[] };

/** Charge d'une resynchronisation (identique en WebSocket et en interrogation HTTP). */
export type Resync = {
  type?: string;
  numero: number;
  depuis: number;
  vue: unknown;
  evenements: Coup[];
  termine: boolean;
  vainqueur_user_id: string | null;
  raison_fin: string | null;
};

/** Transport WebSocket minimal (le `WebSocket` du navigateur le satisfait). */
export interface WebSocketLike {
  send(data: string): void;
  close(): void;
  addEventListener(type: string, écouteur: (événement: unknown) => void): void;
}

export type OptionsCanal = {
  gameId: string;
  /** Dernier numéro appliqué + 1 (0 pour tout recevoir depuis le début). */
  depuis?: number;
  /** Nouvel état autoritaire reçu (resync) : `vue` projetée + numéro courant. */
  onVue: (vue: unknown, numero: number, meta: Resync) => void;
  /** Un coup à appliquer/animer, garanti dans l'ordre et sans doublon. */
  onCoup: (coup: Coup) => void;
  /** Changement de l'état de connexion (pour l'écran). */
  onEtat: (etat: EtatConnexion) => void;
  // --- Points d'injection (tests / environnements sans navigateur) ---
  creerWebSocket?: (url: string) => WebSocketLike;
  fetchSync?: (url: string) => Promise<Response>;
  /** Intervalle d'interrogation en repli (ms). */
  intervalleSondage?: number;
  /** Nombre d'échecs WebSocket consécutifs avant de passer en repli. */
  maxEchecsWs?: number;
  /** Silence maximal (ms) sans message serveur avant de considérer le canal mort. */
  silenceMaxMs?: number;
};

const INTERVALLE_SONDAGE_DEFAUT = 2000;
const MAX_ECHECS_WS_DEFAUT = 3;
// Le serveur bat le cœur toutes les 20 s : au-delà de ce silence, le canal est présumé coupé.
const SILENCE_MAX_DEFAUT = 45000;

/** Construit l'URL WebSocket du canal à partir de la base d'API (relative ou absolue). */
export function urlWebSocket(gameId: string, depuis: number): string {
  const base = getApiBaseUrl();
  let origine: string;
  if (/^https?:\/\//.test(base)) {
    origine = base.replace(/^http/, "ws");
  } else {
    // Base relative (« /api ») : on la résout contre l'origine courante du navigateur.
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    origine = `${proto}//${window.location.host}${base}`;
  }
  return `${origine}/games/${gameId}/ws?depuis=${depuis}`;
}

/** URL du repli en interrogation périodique. */
export function urlSync(gameId: string, depuis: number): string {
  return `${getApiBaseUrl()}/games/${gameId}/sync?depuis=${depuis}`;
}

/**
 * Canal temps réel d'une partie. Appeler `demarrer()` puis `arreter()`.
 *
 * Invariant central : `applique` est le plus grand numéro déjà appliqué. Tout coup de numéro ≤
 * `applique` est un doublon (ignoré) ; le coup attendu est `applique + 1` ; un numéro plus grand
 * est un trou → on redemande une resynchronisation depuis `applique + 1`. Le serveur reste la source
 * de vérité : une resync porte la vue complète, qui prime toujours.
 */
export class CanalPartie {
  private readonly o: Required<
    Pick<OptionsCanal, "gameId" | "onVue" | "onCoup" | "onEtat">
  > &
    OptionsCanal;
  private applique: number;
  private ws: WebSocketLike | null = null;
  private echecsWs = 0;
  private sondage: ReturnType<typeof setInterval> | null = null;
  private veille: ReturnType<typeof setTimeout> | null = null;
  private etat: EtatConnexion = "connexion";
  private arrete = false;

  constructor(options: OptionsCanal) {
    this.o = options as typeof this.o;
    this.applique = (options.depuis ?? 0) - 1;
  }

  /** Ouvre le canal (WebSocket d'abord ; repli en interrogation si impossible). */
  demarrer(): void {
    this.arrete = false;
    this.changerEtat("connexion");
    this.ouvrirWebSocket();
  }

  /** Ferme le canal et libère toutes les ressources (timers, socket). */
  arreter(): void {
    this.arrete = true;
    this.couperVeille();
    this.arreterSondage();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.changerEtat("ferme");
  }

  /** Dernier numéro appliqué (exposé pour l'écran et les tests). */
  get numeroApplique(): number {
    return this.applique;
  }

  // --- WebSocket -------------------------------------------------------------

  private ouvrirWebSocket(): void {
    const fabrique =
      this.o.creerWebSocket ?? ((url: string) => new WebSocket(url) as WebSocketLike);
    let ws: WebSocketLike;
    try {
      ws = fabrique(urlWebSocket(this.o.gameId, this.applique + 1));
    } catch {
      // Le navigateur refuse même d'ouvrir le socket (CSP, protocole) : on compte un échec.
      this.echecWebSocket();
      return;
    }
    this.ws = ws;
    ws.addEventListener("open", () => {
      this.echecsWs = 0;
      this.envoyer({ type: "souscrire", depuis: this.applique + 1 });
      this.armerVeille();
    });
    ws.addEventListener("message", (événement) => {
      this.armerVeille();
      const données = (événement as MessageEvent).data;
      this.traiterMessage(données);
    });
    ws.addEventListener("close", () => this.echecWebSocket());
    ws.addEventListener("error", () => {
      // `error` précède toujours `close` ; on laisse `close` compter l'échec pour ne pas le compter
      // deux fois.
    });
  }

  private echecWebSocket(): void {
    if (this.arrete) return;
    this.couperVeille();
    this.ws = null;
    this.echecsWs += 1;
    if (this.echecsWs >= (this.o.maxEchecsWs ?? MAX_ECHECS_WS_DEFAUT)) {
      this.replierEnSondage();
    } else {
      this.ouvrirWebSocket();
    }
  }

  private envoyer(message: object): void {
    try {
      this.ws?.send(JSON.stringify(message));
    } catch {
      // Socket déjà fermé : l'événement `close` prendra le relais, rien à avaler en silence ici.
    }
  }

  private traiterMessage(données: unknown): void {
    let message: Record<string, unknown>;
    try {
      message = JSON.parse(données as string) as Record<string, unknown>;
    } catch {
      return; // message illisible : ignoré, le numéro de séquence corrigera tout écart
    }
    switch (message.type) {
      case "resync":
        this.appliquerResync(message as unknown as Resync);
        break;
      case "evenement":
        this.appliquerCoup({
          numero: message.numero as number,
          evenements: (message.evenements as unknown[]) ?? [],
        });
        if ("vue" in message) {
          // Un événement porte aussi la vue courante : elle prime (le serveur fait autorité).
          this.o.onVue(message.vue, (message.numero as number) + 1, message as unknown as Resync);
        }
        break;
      case "battement":
        // Le battement porte le numéro courant du serveur : s'il nous dépasse, on a manqué une
        // diffusion → on redemande le reste.
        if (((message.numero as number) ?? -1) - 1 > this.applique) {
          this.envoyer({ type: "resync", depuis: this.applique + 1 });
        }
        break;
      case "pong":
      case "erreur":
        break;
      default:
        break;
    }
    if (this.etat !== "direct") this.changerEtat("direct");
  }

  // --- Application par numéro (dédup + ordre) --------------------------------

  private appliquerResync(resync: Resync): void {
    // La vue est autoritaire au numéro courant : elle reflète déjà tous les coups ≤ numero-1.
    this.o.onVue(resync.vue, resync.numero, resync);
    for (const coup of resync.evenements ?? []) {
      if (coup.numero > this.applique) {
        this.o.onCoup(coup);
      }
    }
    this.applique = Math.max(this.applique, resync.numero - 1);
  }

  private appliquerCoup(coup: Coup): void {
    if (coup.numero <= this.applique) {
      return; // doublon : déjà appliqué
    }
    if (coup.numero > this.applique + 1) {
      // Trou : on ne devine jamais, on redemande tout depuis le prochain attendu.
      this.demanderResync();
      return;
    }
    this.o.onCoup(coup);
    this.applique = coup.numero;
  }

  private demanderResync(): void {
    const depuis = this.applique + 1;
    if (this.ws) {
      this.envoyer({ type: "resync", depuis });
    } else {
      void this.sonderUneFois();
    }
  }

  // --- Repli en interrogation périodique -------------------------------------

  private replierEnSondage(): void {
    if (this.arrete || this.sondage) return;
    this.changerEtat("degrade");
    const intervalle = this.o.intervalleSondage ?? INTERVALLE_SONDAGE_DEFAUT;
    void this.sonderUneFois();
    this.sondage = setInterval(() => void this.sonderUneFois(), intervalle);
  }

  private async sonderUneFois(): Promise<void> {
    if (this.arrete) return;
    const fetcher =
      this.o.fetchSync ??
      ((url: string) => fetch(url, { credentials: "include" }));
    try {
      const réponse = await fetcher(urlSync(this.o.gameId, this.applique + 1));
      if (!réponse.ok) return; // 401/404 : rien à appliquer, le prochain cycle réessaiera
      const resync = (await réponse.json()) as Resync;
      this.appliquerResync(resync);
    } catch {
      // Réseau coupé : on ne conclut pas, le cycle suivant réessaiera (jamais un repli muet définitif)
    }
  }

  private arreterSondage(): void {
    if (this.sondage) {
      clearInterval(this.sondage);
      this.sondage = null;
    }
  }

  // --- Veille de silence (détection de coupure) ------------------------------

  private armerVeille(): void {
    this.couperVeille();
    if (this.arrete) return;
    const silence = this.o.silenceMaxMs ?? SILENCE_MAX_DEFAUT;
    this.veille = setTimeout(() => {
      // Silence trop long : le canal est présumé coupé. On ferme — l'événement `close` relancera un
      // WebSocket, puis le repli si l'échec persiste. La reprise redemandera tout depuis `applique+1`.
      if (this.ws) this.ws.close();
    }, silence);
  }

  private couperVeille(): void {
    if (this.veille) {
      clearTimeout(this.veille);
      this.veille = null;
    }
  }

  private changerEtat(etat: EtatConnexion): void {
    if (this.etat === etat) return;
    this.etat = etat;
    this.o.onEtat(etat);
  }
}
