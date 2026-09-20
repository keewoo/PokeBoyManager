import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HomeContent } from "@/app/home-content";

// `DashboardView` (branche connectée) appelle l'API dès le montage : jamais résolue ici, le
// test ne porte que sur le choix de branche fait par `HomeContent` selon `hasSession`.
vi.mock("@/lib/api/dashboard", () => ({ getDashboard: vi.fn(() => new Promise(() => {})) }));
vi.mock("@/lib/api/profile", () => ({ getProfile: vi.fn(() => new Promise(() => {})) }));

describe("HomeContent", () => {
  it("affiche l'accueil visiteur sans cookie de session", () => {
    render(<HomeContent hasSession={false} />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "On retrouve chaque carte"
    );
  });

  it("affiche le tableau de bord connecté avec un cookie de session", () => {
    render(<HomeContent hasSession={true} />);

    expect(screen.getByText("Chargement…")).toBeInTheDocument();
  });
});
