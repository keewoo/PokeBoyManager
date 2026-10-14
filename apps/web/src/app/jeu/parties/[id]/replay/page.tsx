import type { Metadata } from "next";

import { ReplayView } from "./replay-view";

/** Titre d'onglet de l'écran de replay. */
export const metadata: Metadata = {
  title: "Replay de la partie",
};

/**
 * Le replay d'une partie (`/jeu/parties/{id}/replay`, lot `j-replay`). Route déjà protégée par
 * session (`src/middleware.ts`, préfixe `/jeu`) ; le droit d'accès au jeu (D11) et le droit de
 * regarder CE replay (joueur de la partie, ou partage ouvert par un joueur) sont contrôlés par le
 * serveur — l'écran n'en est que le messager.
 *
 * L'URL est **le lien de partage** : il n'y a pas de jeton à coller dedans, parce qu'un jeton
 * d'URL ouvrirait la partie à qui le détient. Ce qui se partage est un droit, et il se retire.
 *
 * `params` est asynchrone (Next 15) : on l'attend ici pour passer l'identifiant au composant client.
 */
export default async function ReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReplayView gameId={id} />;
}
