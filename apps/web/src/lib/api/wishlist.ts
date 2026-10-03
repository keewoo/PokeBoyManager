import { apiGet, apiJson } from "@/lib/api/client";

/** Une carte souhaitée : la carte visée, un prix cible optionnel, et l'indicateur serveur `target_reached` comparant prix courant et cible. */
export type WishlistItem = {
  id: string;
  card_id: string;
  set_id: string;
  card_name: string;
  card_number: string;
  set_name: string;
  set_code: string;
  rarity: string | null;
  target_price_eur: string | null;
  note: string | null;
  current_price_eur: string | null;
  target_reached: boolean | null;
};

/** Liste la liste de souhaits de l'utilisateur (`GET /me/wishlist`), avec prix courants et atteinte des cibles calculés serveur. */
export function listWishlist(): Promise<{ items: WishlistItem[] }> {
  return apiGet<{ items: WishlistItem[] }>("/me/wishlist");
}

/** Ajoute une carte à la liste de souhaits (`POST /me/wishlist`), avec prix cible et note facultatifs. */
export function createWishlistItem(payload: {
  card_id: string;
  target_price_eur?: string | null;
  note?: string | null;
}): Promise<WishlistItem> {
  return apiJson<WishlistItem>("POST", "/me/wishlist", payload);
}

/** Modifie le prix cible ou la note d'un souhait (`PATCH /me/wishlist/{id}`). */
export function updateWishlistItem(
  itemId: string,
  payload: { target_price_eur?: string | null; note?: string | null }
): Promise<WishlistItem> {
  return apiJson<WishlistItem>("PATCH", `/me/wishlist/${itemId}`, payload);
}

/** Retire une carte de la liste de souhaits (`DELETE /me/wishlist/{id}`) ; borné à l'utilisateur côté serveur. */
export function deleteWishlistItem(itemId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/wishlist/${itemId}`);
}
