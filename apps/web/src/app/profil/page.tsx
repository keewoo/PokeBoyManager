import { Suspense } from "react";

import { ProfileTabs } from "@/components/profile/profile-tabs";

export default function ProfilPage() {
  return (
    <Suspense>
      <ProfileTabs />
    </Suspense>
  );
}
