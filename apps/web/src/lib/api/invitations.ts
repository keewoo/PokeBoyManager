import { apiGet, apiJson } from "@/lib/api/client";

// Contrats miroir de `apps/api/src/pbm_api/routers/invitations.py`. Aucun secret ne transite : le
// jeton d'un lien n'apparaît qu'une fois, à la création (`LienCree.jeton`/`url`), jamais relu. Les
// invitations reçues ne portent que des identifiants — pas de jeton, pas d'empreinte.

// Modes et statuts, miroir du modèle `GameInvitation`.
export const INVITATION_EN_ATTENTE = "en_attente";

export type Invitation = {
  id: string;
  mode: string; // "pseudo" | "lien"
  statut: string; // "en_attente" | "acceptee" | "refusee" | "annulee" | "expiree"
  inviter_user_id: string;
  invitee_user_id: string | null;
  inviter_deck_id: string | null;
  invitee_deck_id: string | null;
};

export type LienCree = Invitation & {
  jeton: string;
  url: string;
};

export type JoueurSalon = {
  user_id: string;
  pseudo: string | null;
  deck: { deck_id: string; nom: string } | null;
};

export type Salon = {
  invitation_id: string;
  statut: string;
  inviter: JoueurSalon;
  invitee: JoueurSalon | null;
};

/** Les invitations reçues par le joueur courant (en attente ou déjà tranchées). */
export function listReceivedInvitations(): Promise<Invitation[]> {
  return apiGet<Invitation[]>("/invitations/recues");
}

/** Crée une invitation par lien partageable ; l'URL (et le jeton) ne sont renvoyés qu'ici. */
export function createInviteLink(deckId?: string): Promise<LienCree> {
  return apiJson<LienCree>("POST", "/invitations/lien", { deck_id: deckId ?? null });
}

/** Accepte une invitation reçue : crée (ou rejoint) le salon d'attente à deux. */
export function acceptInvitation(invitationId: string, deckId?: string): Promise<Salon> {
  return apiJson<Salon>("POST", `/invitations/${invitationId}/accepter`, {
    deck_id: deckId ?? null,
  });
}

/** Refuse une invitation reçue. */
export function refuseInvitation(invitationId: string): Promise<Invitation> {
  return apiJson<Invitation>("POST", `/invitations/${invitationId}/refuser`);
}
