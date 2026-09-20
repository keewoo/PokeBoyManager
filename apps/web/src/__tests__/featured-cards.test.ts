import { afterEach, describe, expect, it, vi } from "vitest";

import { getFeaturedCards } from "@/lib/api/featured-cards";

describe("getFeaturedCards", () => {
  const ORIGINAL_URL = process.env.NEXT_PUBLIC_API_URL;

  afterEach(() => {
    if (ORIGINAL_URL === undefined) delete process.env.NEXT_PUBLIC_API_URL;
    else process.env.NEXT_PUBLIC_API_URL = ORIGINAL_URL;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renvoie une liste vide sans NEXT_PUBLIC_API_URL — aucune origine à appeler côté serveur", async () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const cards = await getFeaturedCards();

    expect(cards).toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("appelle /cards/featured sur l'origine absolue configurée et renvoie les cartes", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.acx-connect.com/api";
    const cards = [{ id: "1", name: "Dracaufeu-EX", number: "6", set_name: "Écarlate et Violet" }];
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => cards,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await getFeaturedCards();

    expect(fetchMock).toHaveBeenCalledWith(
      "https://pokeboy.acx-connect.com/api/cards/featured",
      expect.objectContaining({ next: { revalidate: 3600 } })
    );
    expect(result).toEqual(cards);
  });

  it("renvoie une liste vide (sans lever) quand l'API répond une erreur", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.acx-connect.com/api";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500, statusText: "Internal Server Error" })
    );
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await getFeaturedCards();

    expect(result).toEqual([]);
  });

  it("renvoie une liste vide (sans lever) quand le fetch échoue", async () => {
    process.env.NEXT_PUBLIC_API_URL = "https://pokeboy.acx-connect.com/api";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await getFeaturedCards();

    expect(result).toEqual([]);
  });
});
