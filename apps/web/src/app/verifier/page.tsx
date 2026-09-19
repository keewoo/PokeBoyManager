import { Suspense } from "react";

import { VerifierStatus } from "./verifier-status";

export default function VerifierPage() {
  return (
    <Suspense>
      <VerifierStatus />
    </Suspense>
  );
}
