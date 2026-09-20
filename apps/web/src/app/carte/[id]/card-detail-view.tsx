"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { ApiError } from "@/lib/api/client";
import {
  collectionItemPhotoUrl,
  getCardDetail,
  getCardMyItems,
  type CardDetail,
  type MyCardItem,
} from "@/lib/api/cards";
import { cardImageUrl } from "@/lib/api/validation";

import { HistoryTab } from "./history-tab";
import { InGameTab } from "./in-game-tab";
import { MyItemsTab } from "./my-items-tab";
import { StateTab } from "./state-tab";
import { ValueTab } from "./value-tab";

type TabKey = "valeur" | "etat" | "histoire" | "jeu" | "ex";

const TABS: { key: TabKey; label: string }[] = [
  { key: "valeur", label: "Valeur" },
  { key: "etat", label: "État" },
  { key: "histoire", label: "Histoire" },
  { key: "jeu", label: "En jeu" },
  { key: "ex", label: "Mes exemplaires" },
];

function isTabKey(value: string | null): value is TabKey {
  return TABS.some((tab) => tab.key === value);
}

function eur(value: string): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(
    Number(value)
  );
}

/** Le meilleur candidat pour les faits de l'en-tête (mission point 2, maquette) quand
 * l'utilisateur possède plusieurs exemplaires : celui de plus forte valeur — même choix que
 * `pbm_api.cards.service._best_owned_item`, dont dérive `CardDetail.collection_rank`. */
function pickPrimaryItem(items: MyCardItem[]): MyCardItem | null {
  let best: MyCardItem | null = null;
  for (const item of items) {
    if (item.value_eur === null) continue;
    if (!best || Number(item.value_eur) > Number(best.value_eur)) best = item;
  }
  return best;
}

export function CardDetailView({ cardId }: { cardId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  // État local plutôt que dérivé de `searchParams` à chaque rendu (au contraire des filtres de
  // `/collection`) : changer d'onglet ne redemande rien au serveur, la bascule doit être
  // instantanée — seule l'URL est mise à jour ensuite, pour le partage et le retour arrière.
  const [tab, setTabState] = useState<TabKey>(() => {
    const tabParam = searchParams.get("onglet");
    return isTabKey(tabParam) ? tabParam : "valeur";
  });

  const [card, setCard] = useState<CardDetail | null>(null);
  const [myItems, setMyItems] = useState<MyCardItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imageMode, setImageMode] = useState<"officielle" | "photo">("officielle");

  useEffect(() => {
    let cancelled = false;
    setCard(null);
    setMyItems(null);
    setError(null);
    setImageMode("officielle");
    Promise.all([getCardDetail(cardId), getCardMyItems(cardId)])
      .then(([cardResult, itemsResult]) => {
        if (cancelled) return;
        setCard(cardResult);
        setMyItems(itemsResult);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Impossible de charger cette carte.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [cardId]);

  const primaryItem = useMemo(() => pickPrimaryItem(myItems ?? []), [myItems]);

  function setTab(next: TabKey) {
    setTabState(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set("onglet", next);
    router.replace(`/carte/${cardId}?${params.toString()}`, { scroll: false });
  }

  if (error) {
    return (
      <EmptyState
        title="Carte introuvable"
        description={error}
        action={{ label: "Retour à ma collection", href: "/collection" }}
      />
    );
  }

  if (!card || myItems === null) {
    return <p className="text-sm text-muted-foreground">Chargement…</p>;
  }

  return (
    <div>
      <Link
        href="/collection"
        className="mb-4 inline-block text-sm text-primary hover:underline"
      >
        ← Ma collection
      </Link>

      <div className="grid gap-6 md:grid-cols-[280px_1fr]">
        <div>
          <div className="mb-2 flex gap-1" role="group" aria-label="Image">
            <button
              type="button"
              aria-pressed={imageMode === "officielle"}
              onClick={() => setImageMode("officielle")}
              className={`h-8 rounded-md border border-border px-3 text-xs font-semibold ${imageMode === "officielle" ? "bg-primary text-primary-foreground" : "bg-card text-foreground"}`}
            >
              Image officielle
            </button>
            <button
              type="button"
              aria-pressed={imageMode === "photo"}
              disabled={!primaryItem?.has_photo}
              onClick={() => setImageMode("photo")}
              className={`h-8 rounded-md border border-border px-3 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${imageMode === "photo" ? "bg-primary text-primary-foreground" : "bg-card text-foreground"}`}
            >
              Ma photo
            </button>
          </div>
          {imageMode === "officielle" && card.has_image ? (
            // eslint-disable-next-line @next/next/no-img-element -- image servie par l'API
            <img
              src={cardImageUrl(card.id, "high")}
              alt={card.name}
              className="w-full rounded-lg border border-border object-cover"
            />
          ) : imageMode === "photo" && primaryItem?.has_photo ? (
            // eslint-disable-next-line @next/next/no-img-element -- image servie par l'API
            <img
              src={collectionItemPhotoUrl(primaryItem.id)}
              alt={`Photo de ${card.name}`}
              className="w-full rounded-lg border border-border object-cover"
            />
          ) : (
            <div className="flex aspect-[63/88] w-full items-center justify-center rounded-lg border border-dashed border-border bg-card text-sm text-muted-foreground">
              Aucune image disponible
            </div>
          )}
          <p className="mt-2 text-xs text-muted-foreground">
            Image officielle chargée depuis le catalogue.
          </p>
        </div>

        <div>
          <div className="mb-2 flex flex-wrap gap-2">
            {primaryItem?.counterfeit_suspected && (
              <Badge variant="danger">contrefaçon probable</Badge>
            )}
            {card.rarity && <Badge variant="gold">{card.rarity}</Badge>}
            {primaryItem && <Badge variant="outline">{primaryItem.language}</Badge>}
            {card.collection_rank && (
              <Badge variant="outline">
                n° {card.collection_rank.position} de ta collection
              </Badge>
            )}
            {card.ranking.value_percentile !== null && (
              <Badge variant="outline">
                top {Math.round((1 - card.ranking.value_percentile) * 100)} % de l&apos;extension
              </Badge>
            )}
          </div>
          <h1 className="font-heading text-xl font-bold text-foreground">{card.name}</h1>
          <p className="mt-1 mb-4 text-sm text-muted-foreground">
            {card.set.name} · <span className="font-mono">{card.number}</span>
            {card.hp !== null && ` · ${card.hp} PV`}
          </p>

          <div className="mb-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <p className="text-xs text-muted-foreground">Extension</p>
              <p className="font-semibold text-foreground">{card.set.name}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Sortie</p>
              <p className="font-semibold text-foreground">
                {card.set.release_date
                  ? new Date(card.set.release_date).toLocaleDateString("fr-FR", {
                      month: "long",
                      year: "numeric",
                    })
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Ajoutée le</p>
              <p className="font-semibold text-foreground">
                {primaryItem?.acquired_at
                  ? new Date(primaryItem.acquired_at).toLocaleDateString("fr-FR")
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">État estimé</p>
              <p className="font-semibold text-foreground">
                {primaryItem?.condition_detail?.overall_grade_label ??
                  primaryItem?.condition_grade ??
                  "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Prix d&apos;achat</p>
              <p className="font-mono font-semibold text-foreground">
                {primaryItem?.purchase_price_eur !== null &&
                primaryItem?.purchase_price_eur !== undefined
                  ? eur(primaryItem.purchase_price_eur)
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Plus-value</p>
              <p className="font-mono font-semibold text-foreground">
                {primaryItem?.purchase_price_eur !== null &&
                primaryItem?.purchase_price_eur !== undefined &&
                primaryItem?.value_eur !== null &&
                primaryItem?.value_eur !== undefined ? (
                  (() => {
                    const delta =
                      Number(primaryItem.value_eur) - Number(primaryItem.purchase_price_eur);
                    return (
                      <span className={delta >= 0 ? "text-success" : "text-danger"}>
                        {delta >= 0 ? "+" : ""}
                        {eur(String(delta))}
                      </span>
                    );
                  })()
                ) : (
                  "—"
                )}
              </p>
            </div>
          </div>

          <div className="mb-3 flex flex-wrap gap-1 border-b border-border" role="tablist" aria-label="Sections de la fiche">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`px-3 py-2 text-sm font-semibold ${tab === t.key ? "border-b-2 border-primary text-foreground" : "text-muted-foreground"}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div>
            {tab === "valeur" && <ValueTab cardId={cardId} card={card} primaryItem={primaryItem} />}
            {tab === "etat" && <StateTab item={primaryItem} />}
            {tab === "histoire" && <HistoryTab cardId={cardId} />}
            {tab === "jeu" && <InGameTab cardId={cardId} />}
            {tab === "ex" && <MyItemsTab items={myItems} />}
          </div>
        </div>
      </div>
    </div>
  );
}
