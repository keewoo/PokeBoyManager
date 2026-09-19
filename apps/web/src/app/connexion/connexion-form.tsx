"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AuthLayout } from "@/components/auth/auth-layout";
import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, login } from "@/lib/api/auth";
import { loginSchema, type LoginFormValues } from "@/lib/validation/auth";

const INVALID_CREDENTIALS_MESSAGE = "E-mail ou mot de passe incorrect.";

function safeNextPath(next: string | null): string {
  // `next` vient de l'URL : n'accepter qu'un chemin interne, jamais une URL absolue
  // (protection open-redirect).
  if (!next || !next.startsWith("/") || next.startsWith("//")) return "/";
  return next;
}

export function ConnexionForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = safeNextPath(searchParams.get("next"));
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  async function onSubmit(values: LoginFormValues) {
    setServerError(null);
    try {
      const user = await login(values.email, values.password);
      if (user.must_change_password) {
        router.push("/profil?onglet=securite&mot-de-passe-a-changer=1");
      } else {
        router.push(next);
      }
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setServerError(INVALID_CREDENTIALS_MESSAGE);
      } else if (error instanceof ApiError && error.status === 429) {
        setServerError(error.message);
      } else {
        setServerError("Impossible de te connecter pour le moment.");
      }
    }
  }

  return (
    <AuthLayout title="Connexion">
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

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Mot de passe</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            aria-invalid={!!errors.password}
            {...register("password")}
          />
          {errors.password && <p className="text-xs text-danger">{errors.password.message}</p>}
        </div>

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Connexion…" : "Se connecter"}
        </Button>

        <p className="flex flex-wrap gap-x-1 text-sm text-muted-foreground">
          <Link href="/mot-de-passe-oublie" className="font-medium text-foreground underline">
            Mot de passe oublié
          </Link>
          <span>·</span>
          <Link href="/inscription" className="font-medium text-foreground underline">
            Créer un compte
          </Link>
        </p>
        <p className="text-xs text-muted-foreground">
          Après 5 essais, la connexion se bloque 15 minutes.
        </p>
      </form>
    </AuthLayout>
  );
}
