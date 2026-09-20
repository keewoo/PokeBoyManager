import { Badge } from "@/components/ui/badge";
import { collectionItemPhotoUrl, type MyCardItem } from "@/lib/api/cards";

function eur(value: string): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(
    Number(value)
  );
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("fr-FR") : "—";
}

function purchaseCell(item: MyCardItem): string {
  if (item.purchase_price_eur !== null) return eur(item.purchase_price_eur);
  if (item.purchase_price !== null && item.purchase_currency) {
    return `${item.purchase_price} ${item.purchase_currency} (taux de change indisponible)`;
  }
  return "—";
}

export function MyItemsTab({ items }: { items: MyCardItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Tu ne possèdes aucun exemplaire de cette carte.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="bg-secondary text-left text-xs text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Ajoutée le</th>
            <th className="px-3 py-2 font-medium">Langue</th>
            <th className="px-3 py-2 font-medium">État</th>
            <th className="px-3 py-2 font-medium">Prix d&apos;achat</th>
            <th className="px-3 py-2 font-medium">Valeur</th>
            <th className="px-3 py-2 font-medium">Photo</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className="border-t border-border">
              <td className="px-3 py-2 font-mono text-foreground">
                {formatDate(item.acquired_at)}
              </td>
              <td className="px-3 py-2 text-foreground">{item.language}</td>
              <td className="px-3 py-2 text-foreground">
                {item.condition_detail?.overall_grade_label ?? item.condition_grade ?? "—"}
              </td>
              <td className="px-3 py-2 font-mono text-foreground">{purchaseCell(item)}</td>
              <td className="px-3 py-2 font-mono text-foreground">
                {item.counterfeit_suspected ? (
                  <Badge variant="danger">contrefaçon probable</Badge>
                ) : item.value_eur !== null ? (
                  eur(item.value_eur)
                ) : (
                  "—"
                )}
              </td>
              <td className="px-3 py-2">
                {item.has_photo ? (
                  // eslint-disable-next-line @next/next/no-img-element -- image servie par l'API
                  <img
                    src={collectionItemPhotoUrl(item.id)}
                    alt="Photo de l'exemplaire"
                    className="h-12 w-9 rounded object-cover"
                  />
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
