import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

// Charte PokéBoy : contour teinté, fond transparent. Le badge qualifie une carte, il ne
// doit jamais lui faire concurrence — d'où l'absence d'aplat.
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 font-heading text-xs font-bold tracking-[0.05em] whitespace-nowrap",
  {
    variants: {
      variant: {
        default: "border-[rgba(157,0,255,0.7)] bg-transparent text-violet-clair shadow-[inset_0_0_16px_rgba(157,0,255,0.2)]",
        gold: "border-gold bg-transparent text-gold-foreground shadow-[inset_0_0_16px_rgba(255,215,0,0.16)]",
        success: "border-[rgba(93,211,154,0.6)] bg-transparent text-success-foreground shadow-[inset_0_0_16px_rgba(93,211,154,0.14)]",
        danger: "border-[rgba(255,20,147,0.7)] bg-transparent text-danger-foreground shadow-[inset_0_0_16px_rgba(255,20,147,0.16)]",
        outline: "border-border bg-transparent text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span data-slot="badge" className={cn(badgeVariants({ variant, className }))} {...props} />
  );
}

export { Badge, badgeVariants };
