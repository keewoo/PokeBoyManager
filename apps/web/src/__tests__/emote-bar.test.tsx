import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { EmoteBar } from "@/components/game/emote-bar";
import * as emotesApi from "@/lib/api/emotes";

vi.mock("@/lib/api/emotes", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/emotes")>();
  return { ...actual, getReglagesEmotes: vi.fn(), setReglagesEmotes: vi.fn() };
});

const api = vi.mocked(emotesApi);

/**
 * La palette d'emotes (lot `j-echanges-emotes`, DJ10) — les trois critères d'acceptation du lot se
 * lisent dans ce fichier :
 *
 * - **aucune saisie de texte libre** : on le vérifie sur le DOM rendu, pas sur une relecture du
 *   code (le test statique de `apps/api/tests/test_jeu_emotes_parite.py` garde le reste de
 *   l'interface de plateau) ;
 * - **couper est immédiat et mémorisé** : l'écran se replie au clic (immédiat) et le réglage part
 *   au serveur (mémorisé, côté compte et non côté navigateur) ;
 * - **le débit est limité** : il l'est côté serveur, et son refus **remonte** jusqu'ici avec sa
 *   phrase — un refus muet se lirait comme une panne.
 */
describe("EmoteBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getReglagesEmotes.mockResolvedValue({ recevoir_emotes: true });
    api.setReglagesEmotes.mockImplementation(async (patch) => ({
      recevoir_emotes: patch.recevoir_emotes ?? true,
    }));
  });

  it("n'offre aucun champ de saisie : dix emotes, et rien pour écrire", async () => {
    const { container } = render(<EmoteBar onEnvoyer={() => true} direct />);
    await userEvent.click(await screen.findByTestId("emotes-ouvrir"));

    expect(screen.getAllByTestId(/^emote-(?!bulle)/)).toHaveLength(10);
    // Le cœur de DJ10 : pas de chat libre. Un `<input>`/`<textarea>` ici serait « juste un petit
    // chat », c'est-à-dire un autre produit, avec une obligation de modération.
    expect(container.querySelectorAll("input, textarea")).toHaveLength(0);
    expect(container.querySelectorAll("[contenteditable]")).toHaveLength(0);
  });

  it("envoie le code de l'emote cliquée et referme la palette", async () => {
    const onEnvoyer = vi.fn().mockReturnValue(true);
    render(<EmoteBar onEnvoyer={onEnvoyer} direct />);
    await userEvent.click(await screen.findByTestId("emotes-ouvrir"));
    await userEvent.click(screen.getByTestId("emote-bien_joue"));

    expect(onEnvoyer).toHaveBeenCalledWith("bien_joue");
    expect(screen.queryByTestId("emotes-palette")).toBeNull();
  });

  it("affiche l'emote reçue en clair (pas son code)", async () => {
    render(
      <EmoteBar
        onEnvoyer={() => true}
        direct
        recue={{ code: "ton_tour", de: "adversaire", cle: 1 }}
      />,
    );
    const bulle = await screen.findByTestId("emote-bulle");
    expect(bulle).toHaveTextContent("À toi de jouer");
    expect(bulle).toHaveAttribute("data-de", "adversaire");
  });

  it("couper les emotes est immédiat (l'écran se replie) et mémorisé (le serveur l'écrit)", async () => {
    render(
      <EmoteBar onEnvoyer={() => true} direct recue={{ code: "merci", de: "adversaire", cle: 1 }} />,
    );
    expect(await screen.findByTestId("emote-bulle")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("emotes-interrupteur"));

    // Immédiat : plus de palette, plus de bulle, sans attendre la réponse du serveur.
    await waitFor(() => expect(screen.queryByTestId("emotes-ouvrir")).toBeNull());
    expect(screen.queryByTestId("emote-bulle")).toBeNull();
    // Mémorisé : écrit côté compte, donc valable pour la partie suivante et sur un autre appareil.
    expect(api.setReglagesEmotes).toHaveBeenCalledWith({ recevoir_emotes: false });
    expect(screen.getByTestId("emotes-interrupteur")).toHaveAttribute("aria-checked", "false");
  });

  it("ignore une emote reçue quand le joueur les a coupées", async () => {
    api.getReglagesEmotes.mockResolvedValue({ recevoir_emotes: false });
    render(
      <EmoteBar
        onEnvoyer={() => true}
        direct
        recue={{ code: "bien_joue", de: "adversaire", cle: 1 }}
      />,
    );
    await screen.findByTestId("emotes-interrupteur");
    // Le serveur ne délivre déjà plus rien à ce joueur ; cette garde côté écran couvre l'emote
    // déjà en vol au moment de la coupure.
    expect(screen.queryByTestId("emote-bulle")).toBeNull();
  });

  it("affiche la raison d'un refus du serveur (débit) au lieu de rester muette", async () => {
    render(
      <EmoteBar
        onEnvoyer={() => true}
        direct
        refus={{
          code: "emote_trop_rapide",
          message: "Doucement — attends 2 s avant la prochaine emote.",
        }}
      />,
    );
    expect(await screen.findByTestId("emotes-message")).toHaveTextContent(
      "Doucement — attends 2 s avant la prochaine emote.",
    );
  });

  it("hors connexion directe, la palette ne s'ouvre pas et le dit", async () => {
    render(<EmoteBar onEnvoyer={() => false} direct={false} />);
    const bouton = await screen.findByTestId("emotes-ouvrir");
    expect(bouton).toBeDisabled();
    expect(bouton).toHaveAttribute("title", "Les emotes demandent la connexion directe.");
  });

  it("une lecture de réglage en panne ne prive pas le joueur des emotes (défaut DJ10)", async () => {
    api.getReglagesEmotes.mockRejectedValue(new Error("réseau"));
    render(<EmoteBar onEnvoyer={() => true} direct />);
    expect(await screen.findByTestId("emotes-ouvrir")).toBeInTheDocument();
  });
});
