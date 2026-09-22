import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// Charte PokéBoy : tout ce qui se clique prend la PILULE (`rounded-full`). C'est ce qui
// éloigne l'interface du « plat et carré ». Les hauteurs ne descendent jamais sous 44 px —
// le produit est utilisé au doigt, sur un téléphone, par un enfant de onze ans.
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full font-heading uppercase tracking-[0.09em] transition-shadow disabled:pointer-events-none disabled:opacity-50 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
  {
    variants: {
      variant: {
        // L'action principale : dégradé or vertical, liseré blanc en haut, halo.
        default:
          "border border-transparent bg-[linear-gradient(180deg,#FFF0A0_0%,#FFD700_52%,#E0A800_100%)] font-extrabold text-primary-foreground shadow-[0_0_26px_rgba(255,215,0,0.45),inset_0_1px_0_rgba(255,255,255,0.75)] hover:shadow-[0_0_38px_rgba(255,215,0,0.6),inset_0_1px_0_rgba(255,255,255,0.85)]",
        // L'action secondaire : contour violet, halo intérieur. Jamais de texte violet.
        secondary:
          "border border-[rgba(157,0,255,0.85)] bg-transparent font-semibold text-foreground shadow-[inset_0_0_22px_rgba(157,0,255,0.3)] hover:shadow-[inset_0_0_26px_rgba(157,0,255,0.45),0_0_20px_rgba(157,0,255,0.3)]",
        outline:
          "border border-border bg-transparent font-semibold text-foreground hover:border-[rgba(157,0,255,0.85)] hover:shadow-[inset_0_0_20px_rgba(157,0,255,0.25)]",
        ghost:
          "border border-transparent bg-transparent font-semibold text-muted-foreground hover:text-foreground",
        // Destructif : rose fuchsia en contour seulement — jamais un aplat, il n'a pas
        // le contraste pour porter du texte sombre.
        destructive:
          "border border-[rgba(255,20,147,0.7)] bg-transparent font-semibold text-destructive hover:shadow-[inset_0_0_20px_rgba(255,20,147,0.22)]",
      },
      size: {
        default: "h-12 px-6 text-sm",
        sm: "h-11 px-5 text-xs",
        lg: "h-14 px-8 text-base",
        icon: "h-11 w-11 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
