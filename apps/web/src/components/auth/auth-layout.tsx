export type AuthLayoutProps = {
  title: string;
  description?: string;
  children: React.ReactNode;
};

export function AuthLayout({ title, description, children }: AuthLayoutProps) {
  return (
    <div className="pbm-surface mx-auto grid max-w-4xl overflow-hidden rounded-lg md:grid-cols-2">
      <div className="hidden flex-col justify-between gap-6 bg-screen p-8 text-white md:flex">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/brand/pokeboy-logotype.png"
          alt="PokéBoy — collectionneurs de légendes"
          className="w-full max-w-[280px] drop-shadow-[0_0_26px_rgba(157,0,255,0.55)]"
        />
        <p className="text-sm text-white/80">
          Ton classeur, reconnu carte par carte et coté chaque jour.
        </p>
        <p className="text-xs text-white/60">
          Espace privé : personne d&apos;autre ne voit tes cartes ni tes photos.
        </p>
      </div>

      <div className="flex flex-col gap-6 bg-card p-8">
        <div className="flex flex-col gap-1">
          <h1 className="font-heading text-2xl font-extrabold uppercase tracking-[0.06em] text-gold">{title}</h1>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {children}
      </div>
    </div>
  );
}
