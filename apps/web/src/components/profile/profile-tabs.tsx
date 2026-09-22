"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AiTab } from "@/components/profile/ai-tab";
import { DataTab } from "@/components/profile/data-tab";
import { IdentityTab } from "@/components/profile/identity-tab";
import { SecurityTab } from "@/components/profile/security-tab";
import { FormNotice } from "@/components/auth/form-notice";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api/client";
import { getProfile, type ProfileResponse } from "@/lib/api/profile";

const TABS = [
  { id: "id", label: "Identité" },
  { id: "sec", label: "Sécurité" },
  { id: "ia", label: "Mon IA" },
  { id: "data", label: "Mes données" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function ProfileTabs() {
  const searchParams = useSearchParams();
  // Redirection post-connexion (`must_change_password`, voir `ConnexionForm`) : ouvre
  // directement l'onglet Sécurité avec un rappel visible.
  const forcePasswordChange = searchParams.get("mot-de-passe-a-changer") === "1";
  // `?onglet=` ouvre directement une section : `securite` (redirection post-connexion), `ia`
  // (retour depuis la page d'aide `/profil/aide-cle`) ou `donnees`. Toute autre valeur → Identité.
  const ONGLET_TO_TAB: Record<string, TabId> = { securite: "sec", ia: "ia", donnees: "data" };
  const initialTab: TabId = ONGLET_TO_TAB[searchParams.get("onglet") ?? ""] ?? "id";
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Impossible de charger ton profil.");
      });
  }, []);

  return (
    <div>
      <h2 className="mb-4 font-heading text-2xl font-bold text-foreground">Mon profil</h2>
      <div className="grid grid-cols-1 items-start gap-6 md:grid-cols-[200px_minmax(0,1fr)]">
        <nav aria-label="Sections du profil" className="grid gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              data-slot="profile-tab"
              aria-current={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "rounded-md px-2.5 py-2 text-left text-sm font-medium text-muted-foreground hover:text-foreground",
                activeTab === tab.id && "bg-secondary font-semibold text-foreground ring-1 ring-inset ring-border"
              )}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div>
          {error && <FormNotice variant="error">{error}</FormNotice>}
          {!error && !profile && <p className="text-sm text-muted-foreground">Chargement…</p>}
          {profile && (
            <>
              {activeTab === "id" && (
                <IdentityTab profile={profile} onProfileChange={setProfile} />
              )}
              {activeTab === "sec" && <SecurityTab forcePasswordChange={forcePasswordChange} />}
              {activeTab === "ia" && <AiTab />}
              {activeTab === "data" && <DataTab />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
