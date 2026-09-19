import { z } from "zod";

// 10 caractères minimum : même règle que `pbm_api.security.passwords.is_password_long_enough`.
// La vérification contre les fuites connues (HIBP) reste côté serveur ; le client ne peut
// qu'indiquer une robustesse, jamais garantir l'absence de fuite.
export const PASSWORD_MIN_LENGTH = 10;

// En dessous, l'inscription libre est refusée côté API (RGPD art. 8) — même règle que
// `pbm_api.legal.MINIMUM_AGE_YEARS`.
export const MINIMUM_REGISTRATION_AGE = 15;

export const emailSchema = z.string().trim().min(1, "L'e-mail est requis.").email("Adresse e-mail invalide.");

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Le mot de passe doit contenir au moins ${PASSWORD_MIN_LENGTH} caractères.`);

export const lastNameSchema = z.string().trim().min(1, "Le nom est requis.").max(100);
export const firstNameSchema = z.string().trim().max(100).optional();

function isAtLeast(birthDate: string, years: number): boolean {
  const dob = new Date(birthDate);
  if (Number.isNaN(dob.getTime())) return false;
  const today = new Date();
  const cutoff = new Date(today.getFullYear() - years, today.getMonth(), today.getDate());
  return dob <= cutoff;
}

export const birthDateSchema = z
  .string()
  .min(1, "La date de naissance est requise.")
  .refine((value) => new Date(value) < new Date(), {
    message: "La date de naissance doit être dans le passé.",
  });

export const registrationBirthDateSchema = birthDateSchema.refine(
  (value) => isAtLeast(value, MINIMUM_REGISTRATION_AGE),
  {
    message: `L'inscription libre est réservée aux ${MINIMUM_REGISTRATION_AGE} ans et plus.`,
  }
);

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
export type RegisterFormValues = z.infer<typeof registerSchema>;

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Le mot de passe est requis."),
});
export type LoginFormValues = z.infer<typeof loginSchema>;

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});
export type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z.object({
  password: passwordSchema,
});
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;

export type PasswordStrength = "faible" | "moyenne" | "bonne";

// Indication visuelle seulement — la robustesse réelle (longueur, fuite connue) est
// contrôlée par l'API. Ne jamais bloquer la soumission sur ce seul résultat.
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
