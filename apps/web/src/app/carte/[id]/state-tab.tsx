import { Badge } from "@/components/ui/badge";
import type { ConditionAxis, MyCardItem } from "@/lib/api/cards";

function formatGrade(grade: string | null): string {
  if (!grade) return "—";
  return grade.charAt(0).toUpperCase() + grade.slice(1).replaceAll("_", " ");
}

function AxisBlock({ label, axis }: { label: string; axis: ConditionAxis }) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      {axis ? (
        <>
          <p className="mt-1 font-mono text-lg font-semibold text-foreground">{axis.ratio}</p>
          <p className="text-xs text-muted-foreground">{formatGrade(axis.grade)}</p>
        </>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">Non mesuré</p>
      )}
    </div>
  );
}

function GradeBlock({
  label,
  grade,
  note,
}: {
  label: string;
  grade: string | null;
  note: string | null;
}) {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold text-foreground">{formatGrade(grade)}</p>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

export function StateTab({ item }: { item: MyCardItem | null }) {
  if (!item) {
    return (
      <p className="text-sm text-muted-foreground">
        Ajoute un exemplaire à ta collection pour voir son état estimé.
      </p>
    );
  }

  const detail = item.condition_detail;
  if (!detail) {
    return (
      <p className="text-sm text-muted-foreground">
        {item.condition_grade
          ? `État déclaré : ${formatGrade(item.condition_grade)} (aucune mesure automatique disponible).`
          : "État non estimé pour cet exemplaire."}
      </p>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <AxisBlock label="Centrage horizontal" axis={detail.centering?.horizontal ?? null} />
        <AxisBlock label="Centrage vertical" axis={detail.centering?.vertical ?? null} />
        <GradeBlock
          label="Coins"
          grade={detail.corners?.grade ?? null}
          note={detail.corners?.note ?? null}
        />
        <GradeBlock
          label="Bords"
          grade={detail.edges?.grade ?? null}
          note={detail.edges?.note ?? null}
        />
        <GradeBlock
          label="Surface"
          grade={detail.surface?.grade ?? null}
          note={detail.surface?.note ?? null}
        />
      </div>
      <div className="mt-3 rounded-md border border-border bg-card p-3">
        <p className="font-semibold text-foreground">
          État estimé : {formatGrade(detail.overall_grade)}
          {detail.score_10 !== null && (
            <span className="ml-1 font-mono text-sm text-muted-foreground">
              (≈ {detail.score_10}/10, {detail.overall_grade_label})
            </span>
          )}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{detail.disclaimer}</p>
      </div>
      {detail.counterfeit_suspected && (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-danger/30 bg-danger-background p-3">
          <Badge variant="danger">Contrefaçon probable</Badge>
          <ul className="text-xs text-danger-foreground">
            {detail.counterfeit_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
