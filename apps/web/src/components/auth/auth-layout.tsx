export type AuthLayoutProps = {
  title: string;
  description?: string;
  children: React.ReactNode;
};

export function AuthLayout({ title, description, children }: AuthLayoutProps) {
  return (
    <div className="mx-auto grid max-w-4xl overflow-hidden rounded-lg border border-border md:grid-cols-2">
      <div className="hidden flex-col justify-between gap-6 bg-screen p-8 text-white md:flex">
        <div className="flex items-center gap-2.5 font-pixel text-[11px]">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-white/10">
            <span className="h-3 w-3 rounded-full bg-primary" aria-hidden />
          </span>
          PokeBoyManager
        </div>
        <p className="text-sm text-white/80">
          Ton classeur, reconnu carte par carte et coté chaque jour.
        </p>
        <p className="text-xs text-white/60">
          Espace privé : personne d&apos;autre ne voit tes cartes ni tes photos.
        </p>
      </div>

      <div className="flex flex-col gap-6 bg-card p-8">
        <div className="flex flex-col gap-1">
          <h1 className="font-heading text-2xl font-bold text-foreground">{title}</h1>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {children}
      </div>
    </div>
  );
}
