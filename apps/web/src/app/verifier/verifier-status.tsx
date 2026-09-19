"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { FormNotice } from "@/components/auth/form-notice";
import { ApiError, verifyEmail } from "@/lib/api/auth";

type Status = "loading" | "success" | "error";

export function VerifierStatus() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>(token ? "loading" : "error");
  const [message, setMessage] = useState<string>("Ce lien de vérification est invalide.");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    verifyEmail(token)
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch((error) => {
        if (cancelled) return;
        setMessage(error instanceof ApiError ? error.message : "Ce lien de vérification est invalide.");
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthLayout title="Vérification de l'adresse e-mail">
      {status === "loading" && <p className="text-sm text-muted-foreground">Vérification en cours…</p>}

      {status === "success" && (
        <>
          <FormNotice variant="success">Ton adresse e-mail est vérifiée.</FormNotice>
          <p className="text-sm text-muted-foreground">
            <Link href="/connexion" className="font-medium text-foreground underline">
              Se connecter
            </Link>
          </p>
        </>
      )}

      {status === "error" && (
        <>
          <FormNotice variant="error">{message}</FormNotice>
          <p className="text-sm text-muted-foreground">
            <Link href="/inscription" className="font-medium text-foreground underline">
              Créer un compte
            </Link>
          </p>
        </>
      )}
    </AuthLayout>
  );
}
