import Link from "next/link";

const LEGAL_LINKS = [
  { href: "/mentions-legales", label: "Mentions légales" },
  { href: "/confidentialite", label: "Confidentialité" },
  { href: "/conditions", label: "Conditions générales" },
];

export function LegalFooter() {
  return (
    <footer data-slot="legal-footer" className="mt-16 border-t border-border pt-6 text-sm">
      <nav aria-label="Pages légales" className="flex flex-wrap gap-x-5 gap-y-2">
        {LEGAL_LINKS.map((link) => (
          <Link key={link.href} href={link.href} className="text-muted-foreground hover:text-foreground">
            {link.label}
          </Link>
        ))}
      </nav>
      <p className="mt-3 font-mono text-xs text-muted-foreground">
        PokéBoy n&apos;est pas affilié à Nintendo, Creatures, GAME FREAK ni à The Pokémon Company.
      </p>
    </footer>
  );
}
