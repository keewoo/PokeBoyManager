"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { AvatarPicker } from "@/components/profile/avatar-picker";
import { FormNotice } from "@/components/auth/form-notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import { requestEmailChange, updateIdentity, type ProfileResponse } from "@/lib/api/profile";
import { identitySchema, type IdentityFormValues } from "@/lib/validation/profile";

export type IdentityTabProps = {
  profile: ProfileResponse;
  onProfileChange: (profile: ProfileResponse) => void;
};

export function IdentityTab({ profile, onProfileChange }: IdentityTabProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<IdentityFormValues>({
    resolver: zodResolver(identitySchema),
    defaultValues: {
      pseudo: profile.pseudo ?? "",
      email: profile.email,
      firstName: profile.first_name ?? "",
      lastName: profile.last_name,
      birthDate: profile.birth_date,
    },
  });

  const initials = (profile.pseudo || profile.email).slice(0, 2).toUpperCase();

  async function onSubmit(values: IdentityFormValues) {
    setServerError(null);
    setNotice(null);
    try {
      let updated = profile;
      const identityChanged =
        values.pseudo !== (profile.pseudo ?? "") ||
        values.firstName !== (profile.first_name ?? "") ||
        values.lastName !== profile.last_name ||
        values.birthDate !== profile.birth_date;
      if (identityChanged) {
        updated = await updateIdentity({
          pseudo: values.pseudo,
          firstName: values.firstName,
          lastName: values.lastName,
          birthDate: values.birthDate,
        });
      }
      if (values.email !== profile.email) {
        await requestEmailChange(values.email);
        setNotice(
          "Si cette adresse n'est pas déjà utilisée, un e-mail de confirmation vient d'être " +
            "envoyé. Ton adresse actuelle reste active jusqu'à confirmation."
        );
      }
      onProfileChange(updated);
    } catch (error) {
      setServerError(
        error instanceof ApiError ? error.message : "Impossible d'enregistrer ces informations."
      );
    }
  }

  return (
    <div className="flex max-w-xl flex-col gap-5 rounded-xl border border-border bg-card p-4">
      <AvatarPicker
        hasAvatar={profile.has_avatar}
        initials={initials}
        onUploaded={() => onProfileChange({ ...profile, has_avatar: true })}
      />

      <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {serverError && <FormNotice variant="error">{serverError}</FormNotice>}
        {notice && <FormNotice variant="success">{notice}</FormNotice>}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pseudo">Pseudo</Label>
          <Input id="pseudo" aria-invalid={!!errors.pseudo} {...register("pseudo")} />
          {errors.pseudo && <p className="text-xs text-danger">{errors.pseudo.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="firstName">
            Prénom <span className="font-normal text-muted-foreground">(facultatif)</span>
          </Label>
          <Input id="firstName" {...register("firstName")} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="lastName">Nom</Label>
          <Input id="lastName" aria-invalid={!!errors.lastName} {...register("lastName")} />
          {errors.lastName && <p className="text-xs text-danger">{errors.lastName.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="birthDate">Date de naissance</Label>
          <Input
            id="birthDate"
            type="date"
            aria-invalid={!!errors.birthDate}
            {...register("birthDate")}
          />
          {errors.birthDate && <p className="text-xs text-danger">{errors.birthDate.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">
            E-mail <span className="font-normal text-muted-foreground">
              une nouvelle adresse doit être vérifiée ; l&apos;ancienne est prévenue
            </span>
          </Label>
          <Input id="email" type="email" aria-invalid={!!errors.email} {...register("email")} />
          {errors.email && <p className="text-xs text-danger">{errors.email.message}</p>}
          {profile.pending_email && (
            <p className="text-xs text-muted-foreground">
              En attente de confirmation : {profile.pending_email}
            </p>
          )}
        </div>

        <div>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </div>
      </form>
    </div>
  );
}
