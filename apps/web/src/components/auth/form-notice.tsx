import { cn } from "@/lib/utils";

export type FormNoticeVariant = "error" | "success";

export function FormNotice({
  variant,
  children,
}: {
  variant: FormNoticeVariant;
  children: React.ReactNode;
}) {
  return (
    <p
      role={variant === "error" ? "alert" : "status"}
      className={cn(
        "rounded-md border px-3 py-2 text-sm",
        variant === "error" && "border-danger/30 bg-danger-background text-danger-foreground",
        variant === "success" && "border-success/30 bg-success-background text-success-foreground"
      )}
    >
      {children}
    </p>
  );
}
