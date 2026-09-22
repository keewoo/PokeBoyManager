import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type EmptyStateAction =
  | { label: string; href: string; onClick?: never }
  | { label: string; onClick: () => void; href?: never };

export type EmptyStateProps = {
  title: string;
  description?: string;
  action?: EmptyStateAction;
  className?: string;
};

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[rgba(157,0,255,0.5)] bg-[rgba(6,11,50,0.6)] px-6 py-16 text-center",
        className
      )}
    >
      <h2 className="font-heading text-xl font-bold text-foreground">{title}</h2>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {action &&
        ("href" in action && action.href ? (
          <Button asChild className="mt-2">
            <Link href={action.href}>{action.label}</Link>
          </Button>
        ) : (
          <Button type="button" className="mt-2" onClick={"onClick" in action ? action.onClick : undefined}>
            {action.label}
          </Button>
        ))}
    </div>
  );
}
