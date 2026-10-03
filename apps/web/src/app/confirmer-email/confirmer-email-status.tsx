"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError } from "@/lib/api/client";
import { confirmEmailChange } from "@/lib/api/profile";

type Status = "loading" | "success" | "error";

/**
 * Écran de confirmation d'un changement d'adresse e-mail.
 *
 * Lit le `token` dans l'URL et appelle `confirmEmailChange` (lib/api/profile) une seule
 * fois au montage ; affiche l'un des trois états (en cours / succès / erreur). Sans token,
 * ou si l'API refuse, l'erreur est montrée. La validité du jeton est décidée côté serveur :
 * cet écran ne fait que relayer le verdict.
 */
export function ConfirmerEmailStatus() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>(token ? "loading" : "error");
  const [message, setMessage] = useState<string>("Ce lien de confirmation est invalide.");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    confirmEmailChange(token)
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch((error) => {
        if (cancelled) return;
        setMessage(
          error instanceof ApiError ? error.message : "Ce lien de confirmation est invalide."
        );
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthLayout title="Confirmation de la nouvelle adresse e-mail">
      {status === "loading" && (
        <p className="text-sm text-muted-foreground">Confirmation en cours…</p>
      )}

      {status === "success" && (
        <>
          <FormNotice variant="success">
            Ta nouvelle adresse e-mail est confirmée. Un e-mail a été envoyé à ton ancienne
            adresse pour t&apos;en informer.
          </FormNotice>
          <p className="text-sm text-muted-foreground">
            <Link href="/profil" className="font-medium text-foreground underline">
              Retour au profil
            </Link>
          </p>
        </>
      )}

      {status === "error" && (
        <>
          <FormNotice variant="error">{message}</FormNotice>
          <p className="text-sm text-muted-foreground">
            <Link href="/profil" className="font-medium text-foreground underline">
              Retour au profil
            </Link>
          </p>
        </>
      )}
    </AuthLayout>
  );
}
