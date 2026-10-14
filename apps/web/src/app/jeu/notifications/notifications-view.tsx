"use client";

import { notFound } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { FormNotice } from "@/components/auth/form-notice";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import {
  getNotificationSettings,
  libelleGenre,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  phraseNotification,
  updateNotificationSettings,
  type Notification,
  type ReglagesNotifications,
} from "@/lib/api/notifications";
import { getProfile } from "@/lib/api/profile";

/** Format court d'un horodatage, pour situer une notification sans l'encombrer. */
function quand(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("fr-FR", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Une notification dans la liste : sa phrase, son heure, et le bouton pour la ranger. */
function LigneNotification({
  notification,
  onLue,
}: {
  notification: Notification;
  onLue: (id: string) => void;
}) {
  const lue = notification.lue_at !== null;
  return (
    <li
      data-testid="notification"
      data-genre={notification.genre}
      className={`flex flex-wrap items-center gap-3 rounded-2xl border px-4 py-3 ${
        lue
          ? "border-[rgba(157,0,255,0.25)] text-muted-foreground"
          : "border-[rgba(255,215,0,0.6)] bg-[rgba(255,215,0,0.07)]"
      }`}
    >
      <div className="min-w-0 flex-1">
        <p className="text-sm">{phraseNotification(notification)}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {quand(notification.created_at)}
          {/* Le silence nocturne se dit à l'écran : sans cela, un joueur croirait à une panne de
              notification alors qu'il a lui-même demandé à ne pas être réveillé. */}
          {notification.silencieuse && " · arrivée pendant le silence nocturne"}
        </p>
      </div>
      {!lue && (
        <Button type="button" variant="outline" onClick={() => onLue(notification.id)}>
          Marquer comme lue
        </Button>
      )}
    </li>
  );
}

/**
 * Écran des notifications du jeu (`/jeu/notifications`) : ce que j'ai reçu, et ce que j'accepte de
 * recevoir (lot `j-notifications-jeu`).
 *
 * Un compte sans droit d'accès au jeu reçoit une **page inexistante** (`notFound()`) : l'API lui
 * répond déjà 404 sur toutes les routes du jeu (D11), l'écran ne promet pas une porte qui n'existe
 * pas.
 *
 * L'écran ne décide d'aucune règle : les plafonds viennent du serveur et sont affichés tels quels,
 * et le silence nocturne est appliqué côté serveur — ici on ne fait que le régler et l'expliquer.
 */
export function NotificationsView() {
  const [refuse, setRefuse] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [nbNonLues, setNbNonLues] = useState(0);
  const [reglages, setReglages] = useState<ReglagesNotifications | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  // Autorité d'accès : `game_access` est lu côté serveur. Faux → page inexistante. Un échec de
  // lecture n'est PAS traité comme un refus : on affiche l'erreur, parce que « je n'ai pas pu
  // savoir » et « tu n'as pas le droit » ne sont pas la même chose.
  useEffect(() => {
    let actif = true;
    getProfile()
      .then((profil) => {
        if (!actif) return;
        if (!profil.game_access) setRefuse(true);
      })
      .catch((cause) => {
        if (actif) setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
      });
    return () => {
      actif = false;
    };
  }, []);

  const recharger = useCallback(async () => {
    try {
      const [liste, reg] = await Promise.all([listNotifications(), getNotificationSettings()]);
      setNotifications(liste.notifications);
      setNbNonLues(liste.nb_non_lues);
      setReglages(reg);
      setErreur(null);
    } catch (cause) {
      // Jamais un écran vide muet : on dit que le chargement a échoué, on ne prétend pas
      // « aucune notification » — ce serait un repli qui masque une panne.
      setErreur(cause instanceof ApiError ? cause.message : "Chargement impossible.");
    }
  }, []);

  useEffect(() => {
    if (refuse) return;
    void recharger();
  }, [refuse, recharger]);

  const marquerLue = useCallback(
    async (id: string) => {
      try {
        await markNotificationRead(id);
        await recharger();
      } catch (cause) {
        setErreur(cause instanceof ApiError ? cause.message : "Action impossible.");
      }
    },
    [recharger]
  );

  const marquerToutLu = useCallback(async () => {
    try {
      const liste = await markAllNotificationsRead();
      setNotifications(liste.notifications);
      setNbNonLues(liste.nb_non_lues);
    } catch (cause) {
      setErreur(cause instanceof ApiError ? cause.message : "Action impossible.");
    }
  }, []);

  const appliquer = useCallback(
    async (patch: Parameters<typeof updateNotificationSettings>[0]) => {
      setEnCours(true);
      try {
        setReglages(await updateNotificationSettings(patch));
        setErreur(null);
      } catch (cause) {
        setErreur(cause instanceof ApiError ? cause.message : "Réglage non enregistré.");
      } finally {
        setEnCours(false);
      }
    },
    []
  );

  const basculerGenre = useCallback(
    (genre: string, actif: boolean) => {
      if (!reglages) return;
      const coupes = new Set(reglages.genres_desactives);
      if (actif) coupes.delete(genre);
      else coupes.add(genre);
      void appliquer({ genres_desactives: [...coupes].sort() });
    },
    [reglages, appliquer]
  );

  if (refuse) {
    notFound();
  }

  return (
    <section className="mx-auto w-full max-w-3xl px-4 py-8">
      <header className="mb-6">
        <h1 className="font-heading text-xl font-bold uppercase tracking-[0.08em] text-gold">
          Notifications
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ce qu&apos;on te signale pendant une partie, et ce que tu acceptes de recevoir.
        </p>
      </header>

      {erreur && <FormNotice variant="error">{erreur}</FormNotice>}

      <div className="mt-4 flex items-center justify-between gap-3">
        <h2 className="font-heading text-sm font-semibold uppercase tracking-[0.08em]">
          Reçues {nbNonLues > 0 && <span data-testid="nb-non-lues">({nbNonLues} non lues)</span>}
        </h2>
        {nbNonLues > 0 && (
          <Button type="button" variant="outline" onClick={() => void marquerToutLu()}>
            Tout marquer comme lu
          </Button>
        )}
      </div>

      {notifications.length === 0 ? (
        <EmptyState
          title="Rien à signaler"
          description="Les invitations et les tours de jeu apparaîtront ici."
        />
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {notifications.map((notification) => (
            <LigneNotification
              key={notification.id}
              notification={notification}
              onLue={(id) => void marquerLue(id)}
            />
          ))}
        </ul>
      )}

      {reglages && (
        <div className="mt-10">
          <h2 className="font-heading text-sm font-semibold uppercase tracking-[0.08em]">
            Réglages
          </h2>
          <p className="mt-2 text-xs text-muted-foreground">
            Chaque type se coupe séparément. Une partie ne peut jamais t&apos;envoyer plus de{" "}
            <strong data-testid="plafond-partie">{reglages.plafond_par_partie}</strong>{" "}
            notifications, même si tu les acceptes toutes — on prévient, on ne harcèle pas.
          </p>

          <ul className="mt-4 flex flex-col gap-2">
            {reglages.genres_connus.map((genre) => {
              const actif = !reglages.genres_desactives.includes(genre);
              return (
                <li
                  key={genre}
                  className="flex items-center justify-between gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3"
                >
                  <Label htmlFor={`genre-${genre}`} className="text-sm">
                    {libelleGenre(genre)}
                  </Label>
                  <input
                    id={`genre-${genre}`}
                    type="checkbox"
                    checked={actif}
                    disabled={enCours}
                    onChange={(event) => basculerGenre(genre, event.target.checked)}
                    className="h-5 w-5 accent-[#FFD700]"
                  />
                </li>
              );
            })}
          </ul>

          <div className="mt-6 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="silence-actif" className="text-sm">
                Silence nocturne
              </Label>
              <input
                id="silence-actif"
                type="checkbox"
                checked={reglages.silence_actif}
                disabled={enCours}
                onChange={(event) => void appliquer({ silence_actif: event.target.checked })}
                className="h-5 w-5 accent-[#FFD700]"
              />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Pendant cette plage, rien ne sonne et aucun e-mail ne part — y compris pour une
              invitation. Elle sera là à ton réveil.
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-4">
              <div>
                <Label htmlFor="silence-debut">Début</Label>
                <Input
                  id="silence-debut"
                  type="time"
                  defaultValue={reglages.silence_debut.slice(0, 5)}
                  disabled={enCours || !reglages.silence_actif}
                  onBlur={(event) =>
                    void appliquer({ silence_debut: `${event.target.value}:00` })
                  }
                />
              </div>
              <div>
                <Label htmlFor="silence-fin">Fin</Label>
                <Input
                  id="silence-fin"
                  type="time"
                  defaultValue={reglages.silence_fin.slice(0, 5)}
                  disabled={enCours || !reglages.silence_actif}
                  onBlur={(event) => void appliquer({ silence_fin: `${event.target.value}:00` })}
                />
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-[rgba(157,0,255,0.3)] px-4 py-3">
            <Label htmlFor="relais-email" className="text-sm">
              E-mail pour une invitation
            </Label>
            <input
              id="relais-email"
              type="checkbox"
              checked={reglages.relais_email_invitation}
              disabled={enCours}
              onChange={(event) =>
                void appliquer({ relais_email_invitation: event.target.checked })
              }
              className="h-5 w-5 accent-[#FFD700]"
            />
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Seule l&apos;invitation part par e-mail : elle peut attendre des heures. Un «&nbsp;c&apos;est
            ton tour&nbsp;» par e-mail, non.
          </p>
        </div>
      )}
    </section>
  );
}
