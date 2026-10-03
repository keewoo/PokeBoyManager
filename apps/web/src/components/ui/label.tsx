import * as React from "react";

import { cn } from "@/lib/utils";

// Charte PokéBoy : les étiquettes sont en Exo 2, en capitales espacées, dans le gris
// secondaire — elles annoncent le champ sans lui voler la lecture.
/**
 * Primitive du design system : l'étiquette d'un champ, en capitales espacées et gris
 * secondaire. Se grise avec le champ désactivé (`peer-disabled`). Simple `<label>` —
 * l'association au champ passe par `htmlFor`, à la charge de l'appelant.
 */
function Label({ className, ...props }: React.ComponentProps<"label">) {
  return (
    <label
      data-slot="label"
      className={cn(
        "font-heading text-xs font-bold uppercase leading-none tracking-[0.13em] text-muted-foreground",
        "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}

export { Label };
