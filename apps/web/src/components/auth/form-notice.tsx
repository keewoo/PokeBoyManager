import { cn } from "@/lib/utils";

/** Tonalité d'un message de formulaire : `error` (échec, rôle ARIA `alert`) ou `success` (confirmation, rôle `status`). */
export type FormNoticeVariant = "error" | "success";

/**
 * Encart de message affiché au-dessus ou dans un formulaire. Le `variant` fixe à la fois
 * la couleur et le rôle ARIA (`alert` pour une erreur, `status` pour un succès) afin que
 * les lecteurs d'écran l'annoncent. N'affiche que le texte passé en `children`.
 */
export function FormNotice({
  variant,
  children,
}: {
  variant: FormNoticeVariant;
  children: React.ReactNode;
}) {
  return (
    <p
      role={variant === "error" ? "alert" : "status"}
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        variant === "error" && "border-danger/30 bg-danger-background text-danger-foreground",
        variant === "success" && "border-success/30 bg-success-background text-success-foreground"
      )}
    >
      {children}
    </p>
  );
}
