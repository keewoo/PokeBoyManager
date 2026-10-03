import { z } from "zod";

import { birthDateSchema, emailSchema, firstNameSchema, lastNameSchema, passwordSchema } from "@/lib/validation/auth";

// Même règle que `pbm_api.profile.schemas.UpdatePseudoRequest` côté API.
/** Schéma du pseudo (3-32 caractères, lettres/chiffres/`-`/`_`), même règle que `UpdatePseudoRequest` de l'API. */
export const pseudoSchema = z
  .string()
  .trim()
  .min(3, "Le pseudo doit contenir au moins 3 caractères.")
  .max(32, "Le pseudo doit contenir au plus 32 caractères.")
  .regex(/^[a-zA-Z0-9_-]+$/, "Le pseudo n'accepte que lettres, chiffres, tirets et underscores.");

/** Schéma d'édition de l'identité du profil (pseudo, e-mail, nom, date de naissance — sans contrainte d'âge). */
export const identitySchema = z.object({
  pseudo: pseudoSchema,
  email: emailSchema,
  firstName: firstNameSchema,
  lastName: lastNameSchema,
  // Pas de contrainte d'âge minimum ici : elle ne s'applique qu'à l'inscription libre
  // (voir `pbm_api.profile.service.update_identity`).
  birthDate: birthDateSchema,
});
/** Valeurs validées du formulaire d'identité. */
export type IdentityFormValues = z.infer<typeof identitySchema>;

/** Schéma de changement de mot de passe (ancien non vide + nouveau conforme à {@link passwordSchema}). */
export const changePasswordSchema = z.object({
  currentPassword: z.string().min(1, "Le mot de passe actuel est requis."),
  newPassword: passwordSchema,
});
/** Valeurs validées du formulaire de changement de mot de passe. */
export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>;

/** Schéma de suppression de compte : confirmation par le mot de passe courant (non vide). */
export const deleteAccountSchema = z.object({
  password: z.string().min(1, "Le mot de passe est requis."),
});
/** Valeurs validées du formulaire de suppression de compte. */
export type DeleteAccountFormValues = z.infer<typeof deleteAccountSchema>;
