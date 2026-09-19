import { z } from "zod";

import { birthDateSchema, emailSchema, firstNameSchema, lastNameSchema, passwordSchema } from "@/lib/validation/auth";

// Même règle que `pbm_api.profile.schemas.UpdatePseudoRequest` côté API.
export const pseudoSchema = z
  .string()
  .trim()
  .min(3, "Le pseudo doit contenir au moins 3 caractères.")
  .max(32, "Le pseudo doit contenir au plus 32 caractères.")
  .regex(/^[a-zA-Z0-9_-]+$/, "Le pseudo n'accepte que lettres, chiffres, tirets et underscores.");

export const identitySchema = z.object({
  pseudo: pseudoSchema,
  email: emailSchema,
  firstName: firstNameSchema,
  lastName: lastNameSchema,
  // Pas de contrainte d'âge minimum ici : elle ne s'applique qu'à l'inscription libre
  // (voir `pbm_api.profile.service.update_identity`).
  birthDate: birthDateSchema,
});
export type IdentityFormValues = z.infer<typeof identitySchema>;

export const changePasswordSchema = z.object({
  currentPassword: z.string().min(1, "Le mot de passe actuel est requis."),
  newPassword: passwordSchema,
});
export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>;

export const deleteAccountSchema = z.object({
  password: z.string().min(1, "Le mot de passe est requis."),
});
export type DeleteAccountFormValues = z.infer<typeof deleteAccountSchema>;
