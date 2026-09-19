"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AuthLayout } from "@/components/auth/auth-layout";
import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, forgotPassword } from "@/lib/api/auth";
import { forgotPasswordSchema, type ForgotPasswordFormValues } from "@/lib/validation/auth";

export default function MotDePasseOubliePage() {
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  async function onSubmit(values: ForgotPasswordFormValues) {
    setServerError(null);
    try {
      // Réponse toujours identique côté API, que l'e-mail existe ou non (anti-énumération) :
      // on affiche le même écran de succès quel que soit le compte.
      await forgotPassword(values.email);
      setSubmitted(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setServerError(error.message);
      } else {
        setServerError("Impossible d'envoyer cet e-mail pour le moment.");
      }
    }
  }

  if (submitted) {
    return (
      <AuthLayout title="Vérifie ta boîte mail" description="On y est presque.">
        <FormNotice variant="success">
          Si un compte existe pour cette adresse, un e-mail de réinitialisation vient d&apos;être
          envoyé.
        </FormNotice>
        <p className="text-sm text-muted-foreground">
          <Link href="/connexion" className="font-medium text-foreground underline">
            Retour à la connexion
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Mot de passe oublié"
      description="Indique ton adresse e-mail : si un compte existe, tu recevras un lien de réinitialisation."
    >
      <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {serverError && <FormNotice variant="error">{serverError}</FormNotice>}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">E-mail</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            aria-invalid={!!errors.email}
            {...register("email")}
          />
          {errors.email && <p className="text-xs text-danger">{errors.email.message}</p>}
        </div>

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Envoi…" : "Envoyer le lien de réinitialisation"}
        </Button>

        <p className="text-sm text-muted-foreground">
          <Link href="/connexion" className="font-medium text-foreground underline">
            Retour à la connexion
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
