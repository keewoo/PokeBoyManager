import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardTile, type CardTileProps } from "@/components/card-tile";
import { ConditionBadge, type ConditionGrade } from "@/components/condition-badge";
import { EmptyState } from "@/components/empty-state";
import { RarityBadge, type RarityTier } from "@/components/rarity-badge";
import { ValueDelta } from "@/components/value-delta";

const COLOR_TOKENS = [
  { name: "background", label: "Fond" },
  { name: "foreground", label: "Texte" },
  { name: "card", label: "Surface" },
  { name: "primary", label: "Primaire" },
  { name: "secondary", label: "Secondaire" },
  { name: "muted", label: "Atténué" },
  { name: "border", label: "Bordure" },
  { name: "gold", label: "Or (rareté)" },
  { name: "success", label: "Hausse" },
  { name: "danger", label: "Baisse" },
] as const;

const RARITIES: RarityTier[] = ["commune", "peu-commune", "rare", "rare-holo", "ultra-rare", "secrete"];
const CONDITIONS: ConditionGrade[] = ["mint", "near-mint", "excellent", "bon", "joue", "abime"];

const SAMPLE_CARDS: CardTileProps[] = [
  {
    href: "/carte/1",
    name: "Dracaufeu",
    setName: "Écarlate et Violet",
    number: "006/198",
    price: "142,00 €",
    delta: 8.1,
    rarity: "ultra-rare",
    condition: "near-mint",
  },
  {
    href: "/carte/2",
    name: "Bulbizarre",
    setName: "Base",
    number: "044/102",
    price: "1,20 €",
    delta: -2.4,
    rarity: "commune",
    condition: "bon",
  },
  {
    href: "/carte/3",
    name: "Mewtwo",
    setName: "Jungle",
    number: "010/064",
    price: "38,50 €",
    delta: 0,
    rarity: "rare-holo",
    condition: "excellent",
  },
  {
    href: "/carte/4",
    name: "Pikachu Illustrator",
    setName: "Promo",
    number: "N/A",
    price: "—",
    rarity: "secrete",
    condition: "abime",
  },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="font-heading text-2xl font-bold text-foreground">{title}</h2>
      {children}
    </section>
  );
}

export default function DesignSystemPage() {
  return (
    <div className="flex flex-col gap-14 pb-16">
      <header className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Page interne — recette visuelle
        </p>
        <h1 className="font-heading text-3xl font-bold text-foreground">Design system</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Jetons de couleur, typographies et composants de base de PokéBoy. Cette page
          n&apos;est pas destinée aux utilisateurs finaux.
        </p>
      </header>

      <Section title="Couleurs">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
          {COLOR_TOKENS.map((token) => (
            <div key={token.name} className="flex flex-col gap-2">
              <div
                className="h-16 w-full rounded-lg border border-border"
                style={{ background: `var(--${token.name})` }}
              />
              <div className="text-xs">
                <p className="font-semibold text-foreground">{token.label}</p>
                <p className="font-mono text-muted-foreground">--{token.name}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Typographies">
        <div className="flex flex-col gap-4">
          <p className="font-heading text-4xl font-extrabold uppercase tracking-[0.06em] text-violet-clair">Exo 2 — titres de section</p>
          <p className="font-sans text-base text-foreground">
            Roboto — texte courant de l&apos;interface, lisible pour les descriptions et les formulaires.
          </p>
          <p className="font-mono text-lg text-foreground">JetBrains Mono — 142,00 € · +8,1 % · 006/198</p>
          <p className="pbm-titre text-sm">Press Start 2P — titres courts</p>
        </div>
      </Section>

      <Section title="Boutons">
        <div className="flex flex-wrap gap-3">
          <Button>Défaut</Button>
          <Button variant="secondary">Secondaire</Button>
          <Button variant="outline">Contour</Button>
          <Button variant="ghost">Discret</Button>
          <Button variant="destructive">Destructif</Button>
        </div>
      </Section>

      <Section title="Badges génériques">
        <div className="flex flex-wrap gap-3">
          <Badge>Défaut</Badge>
          <Badge variant="gold">Or</Badge>
          <Badge variant="success">Succès</Badge>
          <Badge variant="danger">Danger</Badge>
          <Badge variant="outline">Contour</Badge>
        </div>
      </Section>

      <Section title="RarityBadge">
        <div className="flex flex-wrap gap-2">
          {RARITIES.map((rarity) => (
            <RarityBadge key={rarity} rarity={rarity} />
          ))}
        </div>
      </Section>

      <Section title="ConditionBadge">
        <div className="flex flex-wrap gap-2">
          {CONDITIONS.map((condition) => (
            <ConditionBadge key={condition} condition={condition} />
          ))}
        </div>
      </Section>

      <Section title="ValueDelta">
        <div className="flex flex-wrap gap-6">
          <ValueDelta value={12.3} />
          <ValueDelta value={-4.2} />
          <ValueDelta value={0} />
        </div>
      </Section>

      <Section title="CardTile">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {SAMPLE_CARDS.map((card) => (
            <CardTile key={card.href} {...card} />
          ))}
        </div>
      </Section>

      <Section title="EmptyState">
        <EmptyState
          title="Aucun résultat"
          description="Exemple d'état vide, utilisé sur les pages sans contenu (collection, recherche...)."
          action={{ label: "Réinitialiser les filtres", href: "/design" }}
        />
      </Section>
    </div>
  );
}
