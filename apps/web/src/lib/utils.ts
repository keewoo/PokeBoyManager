import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Fusionne des classes Tailwind conditionnelles : `clsx` résout les conditions, `twMerge` dédoublonne
 * les utilitaires en conflit (la dernière classe gagne, ex. `px-2 px-4` → `px-4`).
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
