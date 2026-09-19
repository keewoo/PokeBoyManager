"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { FormNotice } from "@/components/auth/form-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { changePassword, listSessions, revokeSession, type SessionResponse } from "@/lib/api/profile";
import { changePasswordSchema, type ChangePasswordFormValues } from "@/lib/validation/profile";

export function SecurityTab() {
  const [serverError, setServerError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionResponse[] | null>(null);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ChangePasswordFormValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { currentPassword: "", newPassword: "" },
  });

  async function loadSessions() {
    try {
      setSessions(await listSessions());
    } catch (error) {
      setSessionsError(
        error instanceof ApiError ? error.message : "Impossible de charger les sessions actives."
      );
    }
  }

  useEffect(() => {
    loadSessions();
  }, []);

  async function onSubmit(values: ChangePasswordFormValues) {
    setServerError(null);
    setNotice(null);
    try {
      await changePassword(values.currentPassword, values.newPassword);
      setNotice("Mot de passe mis à jour. Tes autres sessions ont été déconnectées.");
      reset();
      await loadSessions();
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : "Impossible de changer le mot de passe."
      );
    }
  }

  async function handleRevoke(sessionId: string) {
    setRevokingId(sessionId);
    setSessionsError(null);
    try {
      await revokeSession(sessionId);
      await loadSessions();
    } catch (error) {
      setSessionsError(
        error instanceof ApiError ? error.message : "Impossible de déconnecter cette session."
      );
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
        <h3 className="font-heading text-base font-bold text-foreground">Mot de passe</h3>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
          {serverError && <FormNotice variant="error">{serverError}</FormNotice>}
          {notice && <FormNotice variant="success">{notice}</FormNotice>}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="current-password">Mot de passe actuel</Label>
            <Input
              id="current-password"
              type="password"
              autoComplete="current-password"
              aria-invalid={!!errors.currentPassword}
              {...register("currentPassword")}
            />
            {errors.currentPassword && (
              <p className="text-xs text-danger">{errors.currentPassword.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-password">Nouveau mot de passe</Label>
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              aria-invalid={!!errors.newPassword}
              {...register("newPassword")}
            />
            {errors.newPassword && (
              <p className="text-xs text-danger">{errors.newPassword.message}</p>
            )}
          </div>

          <div>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Changement…" : "Changer le mot de passe"}
            </Button>
          </div>
        </form>
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="font-heading text-base font-bold text-foreground">Sessions actives</h3>
        {sessionsError && <FormNotice variant="error">{sessionsError}</FormNotice>}
        {sessions === null && !sessionsError && (
          <p className="text-sm text-muted-foreground">Chargement…</p>
        )}
        {sessions?.map((session) => (
          <div
            key={session.id}
            className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-3.5"
          >
            <div>
              <p className="text-sm font-semibold text-foreground">
                {session.user_agent ?? "Appareil inconnu"}
              </p>
              <p className="text-xs text-muted-foreground">
                {session.ip_address ?? "IP inconnue"} · connectée le{" "}
                {new Date(session.created_at).toLocaleDateString("fr-FR")}
              </p>
            </div>
            {session.current ? (
              <Badge variant="success">actuelle</Badge>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={revokingId === session.id}
                onClick={() => handleRevoke(session.id)}
              >
                Déconnecter
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
