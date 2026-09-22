import * as React from "react";

import { cn } from "@/lib/utils";

// Cible tactile confortable (20 px de case, dans une zone de 44 px via le label qui
// l'entoure) et couleur d'accent en or, comme toute action de la charte.
function Checkbox({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type="checkbox"
      data-slot="checkbox"
      className={cn(
        "h-5 w-5 shrink-0 rounded-md border border-[rgba(157,0,255,0.5)] bg-[rgba(6,11,50,0.85)] accent-gold",
        "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}

export { Checkbox };
