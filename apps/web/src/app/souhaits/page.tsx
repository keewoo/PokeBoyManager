import { WishlistView } from "./wishlist-view";

/**
 * Route `/souhaits` : la liste de souhaits (wishlist) de l'utilisateur. Simple enveloppe
 * déléguant tout l'affichage et les échanges API au composant client `WishlistView`.
 */
export default function SouhaitsPage() {
  return <WishlistView />;
}
