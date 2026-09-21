import { apiGet, apiJson } from "@/lib/api/client";

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

export function listWishlist(): Promise<{ items: WishlistItem[] }> {
  return apiGet<{ items: WishlistItem[] }>("/me/wishlist");
}

export function createWishlistItem(payload: {
  card_id: string;
  target_price_eur?: string | null;
  note?: string | null;
}): Promise<WishlistItem> {
  return apiJson<WishlistItem>("POST", "/me/wishlist", payload);
}

export function updateWishlistItem(
  itemId: string,
  payload: { target_price_eur?: string | null; note?: string | null }
): Promise<WishlistItem> {
  return apiJson<WishlistItem>("PATCH", `/me/wishlist/${itemId}`, payload);
}

export function deleteWishlistItem(itemId: string): Promise<void> {
  return apiJson<void>("DELETE", `/me/wishlist/${itemId}`);
}
