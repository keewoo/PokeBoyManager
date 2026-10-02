import { beforeEach, describe, expect, it, vi } from "vitest";

import { CanalPartie, type WebSocketLike } from "@/lib/game/realtime";

// Base d'API déterministe (sinon `urlWebSocket` dépendrait de `window.location`).
vi.mock("@/lib/config", () => ({
  getApiBaseUrl: () => "http://api.test",
}));

/** Faux WebSocket piloté à la main : enregistre les envois, émet open/message/close au test. */
class FauxWebSocket implements WebSocketLike {
  envoyes: string[] = [];
  ferme = false;
  private ecouteurs: Record<string, ((e: unknown) => void)[]> = {};

  send(data: string): void {
    this.envoyes.push(data);
  }
  close(): void {
    this.ferme = true;
    this.emettre("close", {});
  }
  addEventListener(type: string, cb: (e: unknown) => void): void {
    (this.ecouteurs[type] ??= []).push(cb);
  }
  private emettre(type: string, ev: unknown): void {
    (this.ecouteurs[type] ?? []).forEach((cb) => cb(ev));
  }
  ouvrir(): void {
    this.emettre("open", {});
  }
  recevoir(obj: unknown): void {
    this.emettre("message", { data: JSON.stringify(obj) });
  }

  get derniersEnvois(): Record<string, unknown>[] {
    return this.envoyes.map((e) => JSON.parse(e));
  }
}

const flush = () => new Promise((r) => setTimeout(r, 0));

function monterCanal(overrides: Partial<Parameters<typeof creerCanal>[0]> = {}) {
  return creerCanal(overrides);
}

function creerCanal(options: {
  ws?: FauxWebSocket;
  fetchSync?: (url: string) => Promise<Response>;
  maxEchecsWs?: number;
  intervalleSondage?: number;
  depuis?: number;
}) {
  const ws = options.ws ?? new FauxWebSocket();
  const coups: { numero: number; evenements: unknown[] }[] = [];
  const vues: { numero: number }[] = [];
  const etats: string[] = [];
  const canal = new CanalPartie({
    gameId: "g1",
    depuis: options.depuis ?? 0,
    onCoup: (c) => coups.push(c),
    onVue: (_v, numero) => vues.push({ numero }),
    onEtat: (e) => etats.push(e),
    creerWebSocket: () => ws,
    fetchSync: options.fetchSync,
    maxEchecsWs: options.maxEchecsWs,
    intervalleSondage: options.intervalleSondage ?? 100000,
  });
  return { canal, ws, coups, vues, etats };
}

describe("CanalPartie — application par numéro de séquence", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("applique une resync puis les coups, dans l'ordre", () => {
    const { canal, ws, coups, vues } = monterCanal();
    canal.demarrer();
    ws.ouvrir();
    ws.recevoir({ type: "resync", numero: 0, depuis: 0, vue: {}, evenements: [] });
    ws.recevoir({ type: "evenement", numero: 0, vue: {}, evenements: ["a"] });
    ws.recevoir({ type: "evenement", numero: 1, vue: {}, evenements: ["b"] });

    expect(coups.map((c) => c.numero)).toEqual([0, 1]);
    expect(vues.length).toBeGreaterThan(0); // la vue autoritaire a été remontée
    canal.arreter();
  });

  it("ignore un coup en double (même numéro)", () => {
    const { canal, ws, coups } = monterCanal();
    canal.demarrer();
    ws.ouvrir();
    ws.recevoir({ type: "evenement", numero: 0, vue: {}, evenements: ["a"] });
    ws.recevoir({ type: "evenement", numero: 0, vue: {}, evenements: ["a"] });

    expect(coups.map((c) => c.numero)).toEqual([0]);
    canal.arreter();
  });

  it("sur un trou de numéro, redemande une resynchronisation sans appliquer le coup", () => {
    const { canal, ws, coups } = monterCanal();
    canal.demarrer();
    ws.ouvrir();
    // On attend le coup 0 ; arrive le coup 1 → trou → on ne devine pas, on redemande.
    ws.recevoir({ type: "evenement", numero: 1, vue: {}, evenements: ["b"] });

    expect(coups).toEqual([]);
    const demandes = ws.derniersEnvois.filter((m) => m.type === "resync");
    expect(demandes).toContainEqual({ type: "resync", depuis: 0 });
    canal.arreter();
  });

  it("un battement en avance déclenche une resynchronisation", () => {
    const { canal, ws } = monterCanal();
    canal.demarrer();
    ws.ouvrir();
    ws.recevoir({ type: "battement", numero: 3 }); // serveur à 3, nous à -1 → on a manqué des coups
    const demandes = ws.derniersEnvois.filter((m) => m.type === "resync");
    expect(demandes).toContainEqual({ type: "resync", depuis: 0 });
    canal.arreter();
  });
});

describe("CanalPartie — repli en interrogation périodique", () => {
  it("passe en « dégradé » et interroge /sync après l'échec du WebSocket", async () => {
    let urlSondee = "";
    const fetchSync = vi.fn(async (url: string) => {
      urlSondee = url;
      return new Response(
        JSON.stringify({ numero: 1, depuis: 0, vue: {}, evenements: [{ numero: 0, evenements: ["x"] }] }),
        { status: 200 },
      );
    });
    const { canal, ws, coups, etats } = monterCanal({ fetchSync, maxEchecsWs: 1 });
    canal.demarrer();
    ws.close(); // le WebSocket échoue : un seul échec suffit à replier (maxEchecsWs=1)
    await flush();

    expect(etats).toContain("degrade");
    expect(fetchSync).toHaveBeenCalledTimes(1);
    expect(urlSondee).toContain("/games/g1/sync?depuis=0");
    expect(coups.map((c) => c.numero)).toEqual([0]); // le coup manqué a bien été rejoué
    canal.arreter();
  });

  it("une réponse /sync non OK ne casse pas le canal (prochain cycle réessaiera)", async () => {
    const fetchSync = vi.fn(async (_url: string) => new Response("", { status: 401 }));
    const { canal, ws, coups } = monterCanal({ fetchSync, maxEchecsWs: 1 });
    canal.demarrer();
    ws.close();
    await flush();

    expect(fetchSync).toHaveBeenCalled();
    expect(coups).toEqual([]); // rien appliqué, mais aucune exception : repli robuste
    canal.arreter();
  });
});
