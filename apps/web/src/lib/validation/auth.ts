import { z } from "zod";

// 10 caractères minimum : même règle que `pbm_api.security.passwords.is_password_long_enough`.
// La vérification contre les fuites connues (HIBP) reste côté serveur ; le client ne peut
// qu'indiquer une robustesse, jamais garantir l'absence de fuite.
/** Longueur minimale d'un mot de passe, même règle que `is_password_long_enough` côté API. */
export const PASSWORD_MIN_LENGTH = 10;

// En dessous, l'inscription libre est refusée côté API (RGPD art. 8) — même règle que
// `pbm_api.legal.MINIMUM_AGE_YEARS`.
/** Âge minimal pour l'inscription libre (RGPD art. 8), aligné sur `MINIMUM_AGE_YEARS` de l'API. */
export const MINIMUM_REGISTRATION_AGE = 15;

/** Schéma d'une adresse e-mail (non vide, format valide) ; brique partagée des formulaires d'auth. */
export const emailSchema = z.string().trim().min(1, "L'e-mail est requis.").email("Adresse e-mail invalide.");

/** Schéma d'un mot de passe à la création (longueur ≥ {@link PASSWORD_MIN_LENGTH}). */
export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Le mot de passe doit contenir au moins ${PASSWORD_MIN_LENGTH} caractères.`);

/** Schéma du nom de famille : requis, 100 caractères max. */
export const lastNameSchema = z.string().trim().min(1, "Le nom est requis.").max(100);
/** Schéma du prénom : facultatif, 100 caractères max. */
export const firstNameSchema = z.string().trim().max(100).optional();

function isAtLeast(birthDate: string, years: number): boolean {
  const dob = new Date(birthDate);
  if (Number.isNaN(dob.getTime())) return false;
  const today = new Date();
  const cutoff = new Date(today.getFullYear() - years, today.getMonth(), today.getDate());
  return dob <= cutoff;
}

/** Schéma de date de naissance : requise et située dans le passé (sans contrainte d'âge, voir plus bas). */
export const birthDateSchema = z
  .string()
  .min(1, "La date de naissance est requise.")
  .refine((value) => new Date(value) < new Date(), {
    message: "La date de naissance doit être dans le passé.",
  });

/** Date de naissance pour l'inscription libre : {@link birthDateSchema} + âge ≥ {@link MINIMUM_REGISTRATION_AGE}. */
export const registrationBirthDateSchema = birthDateSchema.refine(
  (value) => isAtLeast(value, MINIMUM_REGISTRATION_AGE),
  {
    message: `L'inscription libre est réservée aux ${MINIMUM_REGISTRATION_AGE} ans et plus.`,
  }
);

/** Schéma du formulaire d'inscription (e-mail, mot de passe, identité, date de naissance, acceptation CGU). */
export const registerSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
  firstName: firstNameSchema,
  lastName: lastNameSchema,
  birthDate: registrationBirthDateSchema,
  cgu: z.boolean().refine((value) => value, {
    message: "Tu dois accepter les conditions pour continuer.",
  }),
});
/** Valeurs validées du formulaire d'inscription. */
export type RegisterFormValues = z.infer<typeof registerSchema>;

/** Schéma du formulaire de connexion (le mot de passe doit seulement être non vide). */
export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Le mot de passe est requis."),
});
/** Valeurs validées du formulaire de connexion. */
export type LoginFormValues = z.infer<typeof loginSchema>;

/** Schéma de la demande de réinitialisation de mot de passe (e-mail seul). */
export const forgotPasswordSchema = z.object({
  email: emailSchema,
});
/** Valeurs validées du formulaire de mot de passe oublié. */
export type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;

/** Schéma de définition d'un nouveau mot de passe (après lien de réinitialisation). */
export const resetPasswordSchema = z.object({
  password: passwordSchema,
});
/** Valeurs validées du formulaire de nouveau mot de passe. */
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;

/** Niveaux de robustesse affichés à l'utilisateur (indication visuelle, jamais une garantie). */
export type PasswordStrength = "faible" | "moyenne" | "bonne";

// Indication visuelle seulement — la robustesse réelle (longueur, fuite connue) est
// contrôlée par l'API. Ne jamais bloquer la soumission sur ce seul résultat.
/**
 * Estime la robustesse d'un mot de passe d'après sa longueur et la variété de caractères — à seule
 * fin d'affichage. La robustesse réelle (longueur, fuite HIBP) est contrôlée par l'API ; ne jamais
 * bloquer la soumission sur ce seul résultat.
 */
export function estimatePasswordStrength(password: string): PasswordStrength {
  if (password.length < PASSWORD_MIN_LENGTH) return "faible";

  let variety = 0;
  if (/[a-z]/.test(password)) variety += 1;
  if (/[A-Z]/.test(password)) variety += 1;
  if (/[0-9]/.test(password)) variety += 1;
  if (/[^a-zA-Z0-9]/.test(password)) variety += 1;

  if (password.length >= 14 && variety >= 3) return "bonne";
  if (variety >= 2) return "moyenne";
  return "faible";
}
