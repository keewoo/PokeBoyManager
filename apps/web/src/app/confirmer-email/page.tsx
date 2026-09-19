import { Suspense } from "react";

import { ConfirmerEmailStatus } from "./confirmer-email-status";

export default function ConfirmerEmailPage() {
  return (
    <Suspense>
      <ConfirmerEmailStatus />
    </Suspense>
  );
}
