import { estimatePasswordStrength, PASSWORD_MIN_LENGTH } from "@/lib/validation/auth";
import { cn } from "@/lib/utils";

const LEVEL_INDEX = { faible: 1, moyenne: 2, bonne: 3 } as const;

const LEVEL_COLOR = {
  faible: "bg-danger",
  moyenne: "bg-gold",
  bonne: "bg-success",
} as const;

export function PasswordStrengthMeter({ password }: { password: string }) {
  if (!password) return null;

  const strength = estimatePasswordStrength(password);
  const filled = LEVEL_INDEX[strength];

  return (
    <div className="flex flex-col gap-1" aria-live="polite">
      <div className="flex gap-1" role="img" aria-label={`Robustesse : ${strength}`}>
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cn(
              "h-1.5 flex-1 rounded-full bg-muted",
              step <= filled && LEVEL_COLOR[strength]
            )}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Robustesse : {strength} · {PASSWORD_MIN_LENGTH} caractères minimum, contrôlée aussi contre les
        fuites connues à l&apos;envoi.
      </p>
    </div>
  );
}
