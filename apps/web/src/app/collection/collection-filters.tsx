import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CollectionFacets, CollectionFilters as Filters } from "@/lib/api/collection";

export type FilterOption = { value: string; label: string };

function CheckboxGroup({
  legend,
  options,
  selected,
  onToggle,
}: {
  legend: string;
  options: FilterOption[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  if (options.length === 0) return null;
  return (
    <fieldset className="border-t border-border pt-3 first:border-t-0 first:pt-0">
      <legend className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
        {legend}
      </legend>
      <div className="space-y-1.5">
        {options.map((option) => (
          <label key={option.value} className="flex items-center gap-2 text-sm text-foreground">
            <Checkbox
              checked={selected.includes(option.value)}
              onChange={() => onToggle(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function CollectionFiltersPanel({
  facets,
  filters,
  onChange,
  onReset,
}: {
  facets: CollectionFacets | null;
  filters: Filters;
  onChange: (next: Filters) => void;
  onReset: () => void;
}) {
  function toggle(key: keyof Filters, value: string) {
    const current = (filters[key] as string[] | undefined) ?? [];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange({ ...filters, [key]: next });
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <CheckboxGroup
        legend="Extension"
        options={facets?.sets.map((s) => ({ value: s.set_id, label: s.name })) ?? []}
        selected={filters.set_id ?? []}
        onToggle={(value) => toggle("set_id", value)}
      />
      <CheckboxGroup
        legend="Série"
        options={facets?.series.map((s) => ({ value: s, label: s })) ?? []}
        selected={filters.series ?? []}
        onToggle={(value) => toggle("series", value)}
      />
      <CheckboxGroup
        legend="Rareté"
        options={facets?.rarities.map((s) => ({ value: s, label: s })) ?? []}
        selected={filters.rarity ?? []}
        onToggle={(value) => toggle("rarity", value)}
      />
      <CheckboxGroup
        legend="Type"
        options={facets?.card_types.map((s) => ({ value: s, label: s })) ?? []}
        selected={filters.card_type ?? []}
        onToggle={(value) => toggle("card_type", value)}
      />
      <CheckboxGroup
        legend="Langue"
        options={facets?.languages.map((s) => ({ value: s, label: s.toUpperCase() })) ?? []}
        selected={filters.language ?? []}
        onToggle={(value) => toggle("language", value)}
      />
      <CheckboxGroup
        legend="Variante"
        options={facets?.variants.map((s) => ({ value: s, label: s })) ?? []}
        selected={filters.variant ?? []}
        onToggle={(value) => toggle("variant", value)}
      />
      <CheckboxGroup
        legend="État estimé"
        options={facets?.condition_grades.map((s) => ({ value: s, label: s })) ?? []}
        selected={filters.condition_grade ?? []}
        onToggle={(value) => toggle("condition_grade", value)}
      />

      <fieldset className="border-t border-border pt-3">
        <legend className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Valeur (€)
        </legend>
        <div className="flex items-center gap-2">
          <Input
            inputMode="decimal"
            placeholder="min"
            aria-label="Valeur minimale"
            value={filters.value_min ?? ""}
            onChange={(e) => onChange({ ...filters, value_min: e.target.value || undefined })}
          />
          <span className="text-muted-foreground">–</span>
          <Input
            inputMode="decimal"
            placeholder="max"
            aria-label="Valeur maximale"
            value={filters.value_max ?? ""}
            onChange={(e) => onChange({ ...filters, value_max: e.target.value || undefined })}
          />
        </div>
      </fieldset>

      <fieldset className="border-t border-border pt-3">
        <legend className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Date d&rsquo;ajout
        </legend>
        <div className="space-y-2">
          <Label htmlFor="f-acquired-from" className="sr-only">
            Depuis
          </Label>
          <Input
            id="f-acquired-from"
            type="date"
            value={filters.acquired_from ?? ""}
            onChange={(e) => onChange({ ...filters, acquired_from: e.target.value || undefined })}
          />
          <Label htmlFor="f-acquired-to" className="sr-only">
            Jusqu&rsquo;au
          </Label>
          <Input
            id="f-acquired-to"
            type="date"
            value={filters.acquired_to ?? ""}
            onChange={(e) => onChange({ ...filters, acquired_to: e.target.value || undefined })}
          />
        </div>
      </fieldset>

      <fieldset className="border-t border-border pt-3">
        <legend className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
          Autres
        </legend>
        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Checkbox
              checked={filters.duplicates ?? false}
              onChange={(e) => onChange({ ...filters, duplicates: e.target.checked })}
            />
            Doublons
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground">
            <Checkbox
              checked={filters.counterfeit ?? false}
              onChange={(e) => onChange({ ...filters, counterfeit: e.target.checked })}
            />
            Contrefaçons probables
          </label>
        </div>
      </fieldset>

      <Button type="button" variant="ghost" size="sm" onClick={onReset}>
        Effacer les filtres
      </Button>
    </div>
  );
}
