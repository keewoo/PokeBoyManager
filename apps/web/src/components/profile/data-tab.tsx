"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { deleteAccount } from "@/lib/api/profile";
import { downloadCollectionCsv, requestExport } from "@/lib/api/export";
import { deleteAccountSchema, type DeleteAccountFormValues } from "@/lib/validation/profile";

export function DataTab() {
  const [confirming, setConfirming] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [exportPending, setExportPending] = useState(false);
  const [exportMessage, setExportMessage] = useState<{ variant: "success" | "error"; text: string } | null>(
    null
  );
  const [csvPending, setCsvPending] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<DeleteAccountFormValues>({
    resolver: zodResolver(deleteAccountSchema),
    defaultValues: { password: "" },
  });

  async function onSubmit(values: DeleteAccountFormValues) {
    setServerError(null);
    try {
      await deleteAccount(values.password);
      window.location.href = "/";
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : "Impossible de supprimer ce compte."
      );
    }
  }

  async function onRequestExport() {
    setExportPending(true);
    setExportMessage(null);
    try {
      const result = await requestExport();
      setExportMessage(
        result.status === "succeeded"
          ? {
              variant: "success",
              text: "Ton export est prêt : tu vas recevoir un e-mail avec le lien de téléchargement (valable 24 heures).",
            }
          : {
              variant: "error",
              text: "L'export n'a pas pu être préparé. Réessaie dans un instant.",
            }
      );
    } catch (error) {
      setExportMessage({
        variant: "error",
        text: error instanceof ApiError ? error.message : "Impossible de préparer cet export.",
      });
    } finally {
      setExportPending(false);
    }
  }

  async function onDownloadCsv() {
    setCsvPending(true);
    setCsvError(null);
    try {
      await downloadCollectionCsv();
    } catch (error) {
      setCsvError(error instanceof ApiError ? error.message : "Impossible de télécharger ce fichier.");
    } finally {
      setCsvPending(false);
    }
  }

  return (
    <div className="flex max-w-xl flex-col gap-6 rounded-xl border border-border bg-card p-4">
      <div className="flex flex-col gap-2">
        <h3 className="font-heading text-base font-bold text-foreground">Exporter mes données</h3>
        <p className="text-sm text-muted-foreground">
          Collection (JSON et CSV) et photos d&apos;origine, dans un fichier ZIP. Le lien arrive
          par e-mail et reste valable 24 heures.
        </p>
        {exportMessage && <FormNotice variant={exportMessage.variant}>{exportMessage.text}</FormNotice>}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={onRequestExport} disabled={exportPending}>
            {exportPending ? "Préparation…" : "Préparer l'export"}
          </Button>
          <Button type="button" variant="ghost" onClick={onDownloadCsv} disabled={csvPending}>
            {csvPending ? "Téléchargement…" : "Exporter en CSV"}
          </Button>
        </div>
        {csvError && <FormNotice variant="error">{csvError}</FormNotice>}
        <p className="text-xs text-muted-foreground">
          Le CSV seul (sans photos), tout de suite — même format que celui accepté par
          l&apos;import.
        </p>
      </div>

      <div className="flex flex-col gap-2 border-t border-border pt-5">
        <h3 className="font-heading text-base font-bold text-foreground">Supprimer mon compte</h3>
        <p className="text-sm text-muted-foreground">
          Efface définitivement ta collection, tes photos et tes clés IA. Ton mot de passe sera
          demandé.
        </p>

        {!confirming ? (
          <div>
            <Button type="button" variant="destructive" onClick={() => setConfirming(true)}>
              Supprimer mon compte
            </Button>
          </div>
        ) : (
          <form className="flex flex-col gap-3" onSubmit={handleSubmit(onSubmit)} noValidate>
            {serverError && <FormNotice variant="error">{serverError}</FormNotice>}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="delete-password">Mot de passe</Label>
              <Input
                id="delete-password"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!errors.password}
                {...register("password")}
              />
              {errors.password && <p className="text-xs text-danger">{errors.password.message}</p>}
            </div>

            <div className="flex gap-2">
              <Button type="submit" variant="destructive" disabled={isSubmitting}>
                {isSubmitting ? "Suppression…" : "Confirmer la suppression"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                Annuler
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
