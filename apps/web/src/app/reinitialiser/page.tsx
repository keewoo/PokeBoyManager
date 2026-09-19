import { Suspense } from "react";

import { ReinitialiserForm } from "./reinitialiser-form";

export default function ReinitialiserPage() {
  return (
    <Suspense>
      <ReinitialiserForm />
    </Suspense>
  );
}
