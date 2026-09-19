const SLOTS = [
  { id: 1, suspect: false },
  { id: 2, suspect: false },
  { id: 3, suspect: false },
  { id: 4, suspect: false },
  { id: 5, suspect: true },
  { id: 6, suspect: false },
  { id: 7, suspect: false },
  { id: 8, suspect: true },
  { id: 9, suspect: false },
] as const;

const DETECTED_COUNT = SLOTS.length;
const SUSPECT_COUNT = SLOTS.filter((slot) => slot.suspect).length;
const IDENTIFIED_COUNT = DETECTED_COUNT - SUSPECT_COUNT;
const ESTIMATED_VALUE = "312,40 €";

export function ScanDemo() {
  return (
    <div
      data-slot="scan-demo"
      className="relative grid gap-3 rounded-xl bg-screen p-4"
      aria-label="Exemple : une photo de neuf cartes analysée"
    >
      <div className="relative grid grid-cols-3 gap-2">
        {SLOTS.map((slot) => (
          <div
            key={slot.id}
            className={
              "relative aspect-[63/88] rounded-md bg-gradient-to-br from-secondary to-muted " +
              (slot.suspect
                ? "outline outline-2 outline-dashed outline-danger"
                : "outline outline-2 outline-success")
            }
          >
            <span className="absolute -left-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full bg-primary font-mono text-[11px] font-bold text-primary-foreground">
              {slot.id}
            </span>
          </div>
        ))}
        <div
          className="pointer-events-none absolute inset-x-2 top-2 h-0.5 bg-gradient-to-r from-transparent via-success to-transparent motion-safe:animate-pulse"
          aria-hidden
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-xs text-white/80">
        <span>
          {DETECTED_COUNT} cartes détectées · {IDENTIFIED_COUNT} identifiées ·{" "}
          <b className="font-bold text-gold">{SUSPECT_COUNT} contrefaçons probables</b>
        </span>
        <span>
          valeur estimée <b className="font-bold text-gold">{ESTIMATED_VALUE}</b>
        </span>
      </div>
    </div>
  );
}
