"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AuthLayout } from "@/components/auth/auth-layout";
import { FormNotice } from "@/components/auth/form-notice";
import { PasswordStrengthMeter } from "@/components/auth/password-strength-meter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, resetPassword } from "@/lib/api/auth";
import { resetPasswordSchema, type ResetPasswordFormValues } from "@/lib/validation/auth";

export function ReinitialiserForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "" },
  });
  const password = watch("password");

  async function onSubmit(values: ResetPasswordFormValues) {
    if (!token) {
      setServerError("Ce lien de réinitialisation est invalide.");
      return;
    }
    setServerError(null);
    try {
      await resetPassword(token, values.password);
      setSubmitted(true);
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : "Impossible de réinitialiser ce mot de passe."
      );
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Lien invalide">
        <FormNotice variant="error">Ce lien de réinitialisation est invalide.</FormNotice>
        <p className="text-sm text-muted-foreground">
          <Link href="/mot-de-passe-oublie" className="font-medium text-foreground underline">
            Demander un nouveau lien
          </Link>
        </p>
      </AuthLayout>
    );
  }

  if (submitted) {
    return (
      <AuthLayout title="Mot de passe mis à jour">
        <FormNotice variant="success">
          Ton mot de passe a été changé. Tes sessions actives ont été déconnectées par sécurité.
        </FormNotice>
        <p className="text-sm text-muted-foreground">
          <Link href="/connexion" className="font-medium text-foreground underline">
            Se connecter
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Choisir un nouveau mot de passe">
      <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {serverError && <FormNotice variant="error">{serverError}</FormNotice>}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Nouveau mot de passe</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!errors.password}
            {...register("password")}
          />
          <PasswordStrengthMeter password={password ?? ""} />
          {errors.password && <p className="text-xs text-danger">{errors.password.message}</p>}
        </div>

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Mise à jour…" : "Changer le mot de passe"}
        </Button>
      </form>
    </AuthLayout>
  );
}
