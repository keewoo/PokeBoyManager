import * as React from "react";

import { cn } from "@/lib/utils";

// Charte PokéBoy : les champs prennent la pilule comme les boutons, sur un fond plus
// sombre que la surface qui les porte, avec un halo violet INTÉRIEUR — c'est ce qui les
// fait lire comme des creux et non comme des pavés posés dessus.
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "flex h-12 w-full rounded-full border border-[rgba(157,0,255,0.5)] bg-[rgba(6,11,50,0.85)] px-6 text-sm text-foreground",
        "shadow-[inset_0_0_20px_rgba(157,0,255,0.16)]",
        "placeholder:text-muted-foreground outline-none transition-shadow",
        "focus-visible:border-[rgba(255,215,0,0.8)] focus-visible:shadow-[inset_0_0_22px_rgba(255,215,0,0.14),0_0_22px_rgba(255,215,0,0.28)]",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "aria-invalid:border-[rgba(255,20,147,0.8)] aria-invalid:shadow-[inset_0_0_20px_rgba(255,20,147,0.2)]",
        className
      )}
      {...props}
    />
  );
}

export { Input };
