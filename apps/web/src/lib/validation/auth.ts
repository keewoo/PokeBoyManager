import { z } from "zod";

// 10 caractères minimum : même règle que `pbm_api.security.passwords.is_password_long_enough`.
// La vérification contre les fuites connues (HIBP) reste côté serveur ; le client ne peut
// qu'indiquer une robustesse, jamais garantir l'absence de fuite.
export const PASSWORD_MIN_LENGTH = 10;

export const emailSchema = z.string().trim().min(1, "L'e-mail est requis.").email("Adresse e-mail invalide.");

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Le mot de passe doit contenir au moins ${PASSWORD_MIN_LENGTH} caractères.`);

export const registerSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
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
