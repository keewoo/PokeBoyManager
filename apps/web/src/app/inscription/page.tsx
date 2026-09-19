"use client";

import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AuthLayout } from "@/components/auth/auth-layout";
import { FormNotice } from "@/components/auth/form-notice";
import { PasswordStrengthMeter } from "@/components/auth/password-strength-meter";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, registerAccount } from "@/lib/api/auth";
import { registerSchema, type RegisterFormValues } from "@/lib/validation/auth";

export default function InscriptionPage() {
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: "", password: "", firstName: "", lastName: "", birthDate: "", cgu: false },
  });
  const password = watch("password");

  async function onSubmit(values: RegisterFormValues) {
    setServerError(null);
    try {
      await registerAccount({
        email: values.email,
        password: values.password,
        firstName: values.firstName,
        lastName: values.lastName,
        birthDate: values.birthDate,
        acceptTerms: values.cgu,
      });
      setSubmitted(true);
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : "Impossible de créer ton espace pour le moment."
      );
    }
  }

  if (submitted) {
    return (
      <AuthLayout title="Vérifie ta boîte mail" description="On y est presque.">
        <FormNotice variant="success">
          Si cette adresse n&apos;est pas déjà utilisée, un e-mail de vérification vient d&apos;être
          envoyé. Ouvre-le et clique le lien qu&apos;il contient pour activer ton compte.
        </FormNotice>
        <p className="text-sm text-muted-foreground">
          Déjà vérifié ?{" "}
          <Link href="/connexion" className="font-medium text-foreground underline">
            Se connecter
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Créer mon espace"
      description="Il te faut une adresse e-mail et un mot de passe. Tu brancheras ton IA ensuite."
    >
      <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {serverError && <FormNotice variant="error">{serverError}</FormNotice>}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="firstName">
            Prénom <span className="font-normal text-muted-foreground">(facultatif)</span>
          </Label>
          <Input id="firstName" autoComplete="given-name" {...register("firstName")} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="lastName">Nom</Label>
          <Input
            id="lastName"
            autoComplete="family-name"
            aria-invalid={!!errors.lastName}
            {...register("lastName")}
          />
          {errors.lastName && <p className="text-xs text-danger">{errors.lastName.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="birthDate">Date de naissance</Label>
          <Input
            id="birthDate"
            type="date"
            autoComplete="bday"
            aria-invalid={!!errors.birthDate}
            {...register("birthDate")}
          />
          {errors.birthDate && <p className="text-xs text-danger">{errors.birthDate.message}</p>}
        </div>

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
            autoComplete="new-password"
            aria-invalid={!!errors.password}
            {...register("password")}
          />
          <PasswordStrengthMeter password={password ?? ""} />
          {errors.password && <p className="text-xs text-danger">{errors.password.message}</p>}
        </div>

        <div className="flex items-start gap-2">
          <Checkbox id="cgu" className="mt-0.5" {...register("cgu")} />
          <Label htmlFor="cgu" className="font-normal">
            J&apos;accepte les conditions et la politique de confidentialité.
          </Label>
        </div>
        {errors.cgu && <p className="text-xs text-danger">{errors.cgu.message}</p>}

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Création en cours…" : "Créer mon espace"}
        </Button>

        <p className="text-sm text-muted-foreground">
          Déjà inscrit ?{" "}
          <Link href="/connexion" className="font-medium text-foreground underline">
            Se connecter
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
